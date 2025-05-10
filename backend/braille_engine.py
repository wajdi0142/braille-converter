# backend/braille_engine.py
import subprocess
import os
import unicodedata
import re
from collections import OrderedDict
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from backend.config import LOU_TRANSLATE_PATH, TABLES_DIRECTORY
from concurrent.futures import ThreadPoolExecutor
import threading
import shutil
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

class BrailleEngine:
    def __init__(self, lou_path=LOU_TRANSLATE_PATH, tables_dir=TABLES_DIRECTORY):
        self.lou_path = self._check_liblouis(lou_path)
        self.tables_dir = self._check_tables_dir(tables_dir)
        self.custom_table = {}
        self._wrap_cache = OrderedDict()
        self._wrap_cache_max_size = 500
        self._wrap_cache_width = None
        self.load_custom_table()
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.lock = threading.Lock()

    def _check_liblouis(self, default_path):
        paths = [default_path, shutil.which("lou_translate")]
        for path in paths:
            if path and os.path.exists(path):
                try:
                    result = subprocess.run([path, "--version"], capture_output=True, text=True, check=True)
                    if "liblouis" in result.stdout.lower():
                        return os.path.normpath(path)
                except Exception:
                    continue
        QMessageBox.warning(None, "Avertissement", "LibLouis non détecté. Sélectionnez lou_translate.exe.")
        path, _ = QFileDialog.getOpenFileName(None, "Sélectionner lou_translate.exe", "", "Exécutables (*.exe)")
        if path and os.path.exists(path):
            return os.path.normpath(path)
        QMessageBox.critical(None, "Erreur", "Chemin LibLouis invalide. Fermeture.")
        import sys
        sys.exit(1)

    def _check_tables_dir(self, tables_dir):
        if os.path.exists(tables_dir):
            return tables_dir
        default_dir = os.path.join(os.path.dirname(self.lou_path), "..", "share", "liblouis", "tables")
        if os.path.exists(default_dir):
            return default_dir
        QMessageBox.critical(None, "Erreur", f"Répertoire des tables non trouvé : {tables_dir}")
        import sys
        sys.exit(1)

    def load_custom_table(self):
        self.custom_table.clear()
        custom_file = "custom_table.txt"
        if os.path.exists(custom_file):
            with open(custom_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        char, braille = line.strip().split(",", 1)
                        if len(char) >= 1 and all('\u2800' <= c <= '\u28FF' for c in braille):
                            self.custom_table[char] = braille
                    except ValueError as e:
                        print(f"Format incorrect dans {custom_file} : {line.strip()} - {str(e)}")

    def update_custom_table(self):
        self.load_custom_table()
        with self.lock:
            self._wrap_cache.clear()

    def get_available_tables(self):
        all_tables = [f for f in os.listdir(self.tables_dir) if f.endswith((".utb", ".ctb"))]
        table_names = {
            "Arabe (grade 1)": "ar-ar-g1.utb",
            "Français (grade 1)": "fr-bfu-comp6.utb",
            "Français (grade 2)": "fr-bfu-g2.ctb",
            "Anglais (grade 1)": "en-us-g1.ctb",
            "Anglais (grade 2)": "en-us-g2.ctb",
        }
        return {name: os.path.join(self.tables_dir, filename) for name, filename in table_names.items() if filename in all_tables}

    def wrap_text_by_sentence(self, text, width=33, preserve_newlines=True):
        """
        Formate le texte en respectant les contraintes suivantes :
        - Ne coupe pas les mots (retour à la ligne uniquement après un espace).
        - Ne divise les phrases qu'après un point (.), sauf si la ligne dépasse la largeur maximale.
        - Préserve les espaces multiples.
        
        Args:
            text (str): Texte à formater.
            width (int): Largeur maximale de la ligne en caractères.
            preserve_newlines (bool): Conserver les sauts de ligne existants.
        
        Returns:
            str: Texte formaté avec des retours à la ligne appropriés.
        """
        logging.debug(f"wrap_text_by_sentence called with text='{text[:50]}...', width={width}, preserve_newlines={preserve_newlines}")
        if not text or width < 1:
            return ""

        cache_key = (text, width, "sentence", preserve_newlines)
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                logging.debug("Returning cached result")
                return self._wrap_cache[cache_key]

        # Divise le texte en lignes si preserve_newlines est True
        lines = text.split("\n") if preserve_newlines else [text]
        wrapped_lines = []

        for line in lines:
            if not line:
                wrapped_lines.append("")
                continue

            # Divise en segments (phrases ou espaces multiples)
            segments = re.split(r'(\s+|[^\s.]+(?:\.[^\s.]|$))', line)
            segments = [s for s in segments if s]  # Supprime les segments vides
            current_line = ""
            line_segments = []

            for segment in segments:
                if segment.isspace():
                    # Gérer les espaces multiples
                    if len(current_line) + len(segment) <= width:
                        current_line += segment
                    else:
                        if current_line:
                            line_segments.append(current_line.rstrip())
                        current_line = segment.lstrip()
                    continue

                # Gérer les phrases ou mots
                if len(current_line) + len(segment) <= width:
                    current_line += segment
                else:
                    if current_line:
                        line_segments.append(current_line.rstrip())
                        current_line = segment
                    else:
                        # Si le segment est trop long, le couper
                        while len(segment) > width:
                            line_segments.append(segment[:width])
                            segment = segment[width:]
                        current_line = segment

            if current_line:
                line_segments.append(current_line.rstrip())

            wrapped_lines.extend(line_segments)

        result = "\n".join(wrapped_lines).rstrip()
        logging.debug(f"Formatted text: {result[:100]}...")
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def wrap_text_plain(self, text, width=33, preserve_newlines=True):
        if not text:
            return ""
        cache_key = (text, width, "plain", preserve_newlines)
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                return self._wrap_cache[cache_key]

        lines = text.split("\n") if preserve_newlines else [text.replace("\n", " ")]
        wrapped_lines = []

        for line in lines:
            if not line.strip():
                wrapped_lines.append("")
                continue
            words = re.split(r'(\s+)', line)  # Preserve spaces
            current_line = []
            current_length = 0

            for segment in words:
                segment_length = len(segment)
                if segment.isspace():
                    if current_length + segment_length <= width:
                        current_line.append(segment)
                        current_length += segment_length
                    continue
                if current_length + segment_length <= width:
                    current_line.append(segment)
                    current_length += segment_length
                else:
                    if current_line:
                        wrapped_lines.append("".join(current_line).rstrip())
                    if segment_length > width:
                        while segment:
                            if len(segment) <= width:
                                current_line = [segment]
                                current_length = len(segment)
                                break
                            wrapped_lines.append(segment[:width])
                            segment = segment[width:]
                    else:
                        current_line = [segment]
                        current_length = segment_length
            if current_line:
                wrapped_lines.append("".join(current_line).rstrip())

        result = "\n".join(wrapped_lines)
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def wrap_text(self, text, width=33, preserve_newlines=True):
        if not text:
            return ""
        cache_key = (text, width, "braille", preserve_newlines)
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                return self._wrap_cache[cache_key]

        lines = text.split("\n") if preserve_newlines else [text.replace("\n", " ")]
        wrapped_lines = []

        for line in lines:
            if not line.strip():
                wrapped_lines.append("")
                continue
            words = re.split(r'(\s+)', line)  # Preserve spaces
            current_line = []
            current_length = 0

            for segment in words:
                segment_length = len(segment)
                if segment.isspace():
                    if current_length + segment_length <= width:
                        current_line.append(segment)
                        current_length += segment_length
                    continue
                if current_length + segment_length <= width:
                    current_line.append(segment)
                    current_length += segment_length
                else:
                    if current_line:
                        wrapped_lines.append("".join(current_line).rstrip())
                    if segment_length > width:
                        while segment:
                            if len(segment) <= width:
                                current_line = [segment]
                                current_length = len(segment)
                                break
                            wrapped_lines.append(segment[:width])
                            segment = segment[width:]
                    else:
                        current_line = [segment]
                        current_length = segment_length
            if current_line:
                wrapped_lines.append("".join(current_line).rstrip())

        result = "\n".join(wrapped_lines)
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def sync_lines(self, text, braille, width=33, preserve_newlines=True):
        cache_key = (text, braille, width, "sync", preserve_newlines)
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                return self._wrap_cache[cache_key]

        text_lines = text.split('\n') if preserve_newlines else [text.replace('\n', ' ')]
        braille_lines = braille.split('\n') if preserve_newlines else [braille.replace('\n', ' ')]
        synced_text = []
        synced_braille = []
        max_lines = max(len(text_lines), len(braille_lines))

        for i in range(max_lines):
            text_line = text_lines[i] if i < len(text_lines) else ""
            braille_line = braille_lines[i] if i < len(braille_lines) else ""

            if not text_line.strip() and not braille_line.strip():
                synced_text.append("")
                synced_braille.append("")
                continue

            wrapped_text = self.wrap_text_by_sentence(text_line, width, preserve_newlines=False)
            wrapped_braille = self.wrap_text_by_sentence(braille_line, width, preserve_newlines=False)
            synced_text.append(wrapped_text.rstrip())
            synced_braille.append(wrapped_braille.rstrip())

        result = ("\n".join(synced_text).rstrip(), "\n".join(synced_braille).rstrip())
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def _process_batch(self, batch, table_path, capitalize):
        cmd = [self.lou_path, "--forward", table_path]
        if capitalize:
            cmd.append("--caps-mode=uc")
        cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
        try:
            result = subprocess.run(
                cmd,
                input=batch,
                text=True,
                capture_output=True,
                encoding="utf-8",
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return result.stdout.rstrip("\n")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Erreur LibLouis: {e.stderr}")

    def to_braille(self, text, table_path, line_width=33, capitalize=False, section_separator="\u28CD"):
        if not self.lou_path or not text:
            return ""

        try:
            text = unicodedata.normalize("NFC", text)
            input_lines = text.split("\n")
            braille_lines = []
            batch_size = 50
            batches = []
            current_batch = []
            empty_line_positions = []

            for idx, line in enumerate(input_lines):
                if not line.strip():
                    empty_line_positions.append(idx)
                    if current_batch:
                        batches.append("\n".join(current_batch))
                        current_batch = []
                    continue
                current_batch.append(line)
                if len(current_batch) >= batch_size:
                    batches.append("\n".join(current_batch))
                    current_batch = []
            if current_batch:
                batches.append("\n".join(current_batch))

            for i, batch in enumerate(batches):
                for char, braille in self.custom_table.items():
                    batch = batch.replace(char, braille)
                batches[i] = batch

            batch_results = []
            if batches:
                futures = [self.executor.submit(self._process_batch, batch, table_path, capitalize) for batch in batches]
                for future in futures:
                    batch_results.append(future.result())

            braille_non_empty = []
            for batch_result in batch_results:
                braille_non_empty.extend([line for line in batch_result.split("\n") if line.strip()])

            braille_result = []
            non_empty_idx = 0
            for idx in range(len(input_lines)):
                if idx in empty_line_positions:
                    braille_result.append("")
                else:
                    if non_empty_idx < len(braille_non_empty):
                        line = self.ensure_readability(braille_non_empty[non_empty_idx])
                        line = self.wrap_text_by_sentence(line, line_width, preserve_newlines=True)
                        braille_result.append(line)
                        non_empty_idx += 1

            braille_output = "\n".join(braille_result).rstrip()
            synced_text, synced_braille = self.sync_lines(text, braille_output, line_width, preserve_newlines=True)
            if section_separator:
                synced_braille = synced_braille.replace("\n\n", f"\n{section_separator}\n")
            return synced_braille.rstrip()
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en braille : {e}")
            return ""

    def _process_batch_backward(self, batch, table_path):
        cmd = [self.lou_path, "--backward", table_path]
        cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
        try:
            result = subprocess.run(
                cmd,
                input=batch,
                text=True,
                capture_output=True,
                encoding="utf-8",
                check=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            return result.stdout.rstrip("\n")
        except subprocess.CalledProcessError as e:
            raise Exception(f"Erreur LibLouis: {e.stderr}")

    def from_braille(self, braille_text, table_path, line_width=33):
        if not self.lou_path or not braille_text:
            return ""

        try:
            input_lines = braille_text.split("\n")
            text_lines = []
            batch_size = 50
            batches = []
            current_batch = []
            empty_line_positions = []

            for idx, line in enumerate(input_lines):
                if not line.strip():
                    empty_line_positions.append(idx)
                    if current_batch:
                        batches.append("\n".join(current_batch))
                        current_batch = []
                    continue
                current_batch.append(line)
                if len(current_batch) >= batch_size:
                    batches.append("\n".join(current_batch))
                    current_batch = []
            if current_batch:
                batches.append("\n".join(current_batch))

            batch_results = []
            if batches:
                futures = [self.executor.submit(self._process_batch_backward, batch, table_path) for batch in batches]
                for future in futures:
                    batch_results.append(future.result())

            text_non_empty = []
            for batch_result in batch_results:
                text_non_empty.extend([line for line in batch_result.split("\n") if line.strip()])

            text_result = []
            non_empty_idx = 0
            for idx in range(len(input_lines)):
                if idx in empty_line_positions:
                    text_result.append("")
                else:
                    if non_empty_idx < len(text_non_empty):
                        text = text_non_empty[non_empty_idx]
                        for char, braille in self.custom_table.items():
                            text = text.replace(braille, char)
                        text = self.wrap_text_by_sentence(text, line_width, preserve_newlines=True)
                        text_result.append(text)
                        non_empty_idx += 1

            text_output = "\n".join(text_result).rstrip()
            synced_text, synced_braille = self.sync_lines(text_output, braille_text, line_width, preserve_newlines=True)
            return synced_text.rstrip()
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en texte : {e}")
            return ""

    def ensure_readability(self, braille_text):
        return braille_text.rstrip()

    def __del__(self):
        self.executor.shutdown(wait=True)