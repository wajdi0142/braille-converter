import subprocess
import os
import unicodedata
from collections import OrderedDict
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from backend.config import LOU_TRANSLATE_PATH, TABLES_DIRECTORY
from concurrent.futures import ThreadPoolExecutor
import threading

class BrailleEngine:
    def __init__(self, lou_path=LOU_TRANSLATE_PATH, tables_dir=TABLES_DIRECTORY):
        self.lou_path = self._check_liblouis(lou_path)
        self.tables_dir = tables_dir
        self.custom_table = {}
        # Cache avec limite (LRU)
        self._wrap_cache = OrderedDict()
        self._wrap_cache_max_size = 500  # Limite à 500 entrées
        self._wrap_cache_width = None
        self.load_custom_table()
        # Pool de threads pour parallélisation
        self.executor = ThreadPoolExecutor(max_workers=4)
        self.lock = threading.Lock()

    def _check_liblouis(self, default_path):
        if os.path.exists(default_path):
            try:
                result = subprocess.run([default_path, "--version"], capture_output=True, text=True)
                if "liblouis" in result.stdout.lower():
                    return default_path
            except Exception:
                pass
        QMessageBox.warning(None, "Avertissement", "LibLouis non détecté au chemin par défaut. Sélectionnez lou_translate.exe.")
        path, _ = QFileDialog.getOpenFileName(None, "Sélectionner lou_translate.exe", "", "Exécutables (*.exe)")
        if path and os.path.exists(path):
            return os.path.normpath(path)
        QMessageBox.critical(None, "Erreur", "Chemin LibLouis invalide. Fermeture.")
        import sys
        sys.exit(1)

    def load_custom_table(self):
        self.custom_table.clear()
        custom_file = "custom_table.txt"
        if os.path.exists(custom_file):
            with open(custom_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        char, braille = line.strip().split(",")
                        if len(char) >= 1 and all('\u2800' <= c <= '\u28FF' for c in braille):
                            self.custom_table[char] = braille
                    except ValueError:
                        print(f"Format incorrect dans {custom_file} : {line.strip()}")

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

    def wrap_text_plain(self, text, width=80):
        """Format plain text to respect line width without splitting words, ultra-optimisé."""
        if not text:
            return ""

        # Vérifier le cache
        cache_key = (text, width, "plain")
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                return self._wrap_cache[cache_key]

        lines = text.split("\n")
        wrapped_lines = []
        for line in lines:
            if len(line) <= width:
                wrapped_lines.append(line.rstrip())
                continue

            current_line = []
            current_length = 0
            words = line.split(" ")
            for word in words:
                if not word:
                    continue
                word_length = len(word)

                if current_length + word_length + (1 if current_line else 0) <= width:
                    if current_line:
                        current_line.append(" ")
                        current_length += 1
                    current_line.append(word)
                    current_length += word_length
                else:
                    if current_line:
                        wrapped_lines.append("".join(current_line))
                    if word_length > width:
                        while word:
                            if len(word) <= width:
                                current_line = [word]
                                current_length = len(word)
                                break
                            else:
                                wrapped_lines.append(word[:width])
                                word = word[width:]
                                current_length = 0
                    else:
                        current_line = [word]
                        current_length = word_length

            if current_line:
                wrapped_lines.append("".join(current_line))

        result = "\n".join(wrapped_lines)
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def wrap_text(self, text, width=40):
        """Format braille text to respect line width without splitting words, ultra-optimisé."""
        if not text:
            return ""

        # Vérifier le cache
        cache_key = (text, width, "braille")
        with self.lock:
            if cache_key in self._wrap_cache and self._wrap_cache_width == width:
                return self._wrap_cache[cache_key]

        lines = text.split("\n")
        wrapped_lines = []
        for line in lines:
            if len(line) <= width:
                wrapped_lines.append(line.rstrip())
                continue

            current_line = []
            current_length = 0
            words = line.split(" ")
            for word in words:
                if not word:
                    continue
                word_length = len(word)

                if current_length + word_length + (1 if current_line else 0) <= width:
                    if current_line:
                        current_line.append(" ")
                        current_length += 1
                    current_line.append(word)
                    current_length += word_length
                else:
                    if current_line:
                        wrapped_lines.append("".join(current_line))
                    if word_length > width:
                        while word:
                            if len(word) <= width:
                                current_line = [word]
                                current_length = len(word)
                                break
                            else:
                                wrapped_lines.append(word[:width])
                                word = word[width:]
                                current_length = 0
                    else:
                        current_line = [word]
                        current_length = word_length

            if current_line:
                wrapped_lines.append("".join(current_line))

        result = "\n".join(wrapped_lines)
        with self.lock:
            self._wrap_cache[cache_key] = result
            self._wrap_cache_width = width
            if len(self._wrap_cache) > self._wrap_cache_max_size:
                self._wrap_cache.popitem(last=False)
        return result

    def _process_batch(self, batch, table_path, capitalize):
        """Traiter un lot de lignes avec LibLouis via subprocess."""
        cmd = [self.lou_path, "--forward", table_path]
        if capitalize:
            cmd.append("--caps-mode=uc")
        cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
        result = subprocess.run(
            cmd,
            input=batch,
            text=True,
            capture_output=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        if result.stderr:
            raise Exception(result.stderr)
        return result.stdout.rstrip("\n")

    def to_braille(self, text, table_path, line_width=40, capitalize=False, section_separator="\u28CD"):
        if not self.lou_path or not text:
            return ""

        try:
            text = unicodedata.normalize("NFC", text)
            input_lines = text.split("\n")
            braille_lines = []
            batch_size = 50  # Taille des lots pour moins d'appels
            batches = []
            current_batch = []
            empty_line_positions = []

            # Préparer les lots
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

            # Appliquer les remplacements de la table personnalisée sur les lots
            for i, batch in enumerate(batches):
                for char, braille in self.custom_table.items():
                    batch = batch.replace(char, braille)
                batches[i] = batch

            # Traiter les lots en parallèle avec LibLouis
            batch_results = []
            if batches:
                futures = [self.executor.submit(self._process_batch, batch, table_path, capitalize) for batch in batches]
                for future in futures:
                    batch_results.append(future.result())

            # Combiner les résultats
            braille_non_empty = []
            for batch_result in batch_results:
                braille_non_empty.extend(batch_result.split("\n"))

            # Réinsérer les lignes vides
            braille_result = []
            non_empty_idx = 0
            for idx in range(len(input_lines)):
                if idx in empty_line_positions:
                    braille_result.append("")
                else:
                    if non_empty_idx < len(braille_non_empty):
                        line = self.ensure_readability(braille_non_empty[non_empty_idx])
                        line = self.wrap_text(line, line_width)
                        braille_result.append(line)
                        non_empty_idx += 1

            braille_output = "\n".join(braille_result)
            if section_separator:
                braille_output = braille_output.replace("\n\n", f"\n{section_separator}\n")
            return braille_output
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en braille : {e}")
            return ""

    def _process_batch_backward(self, batch, table_path):
        """Traiter un lot de lignes pour la conversion inverse avec LibLouis."""
        cmd = [self.lou_path, "--backward", table_path]
        cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
        result = subprocess.run(
            cmd,
            input=batch,
            text=True,
            capture_output=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        )
        if result.stderr:
            raise Exception(result.stderr)
        return result.stdout.rstrip("\n")

    def from_braille(self, braille_text, table_path, line_width=80):
        if not self.lou_path or not braille_text:
            return ""

        try:
            input_lines = braille_text.split("\n")
            text_lines = []
            batch_size = 50
            batches = []
            current_batch = []
            empty_line_positions = []

            # Préparer les lots
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

            # Traiter les lots en parallèle
            batch_results = []
            if batches:
                futures = [self.executor.submit(self._process_batch_backward, batch, table_path) for batch in batches]
                for future in futures:
                    batch_results.append(future.result())

            # Combiner les résultats
            text_non_empty = []
            for batch_result in batch_results:
                text_non_empty.extend(batch_result.split("\n"))

            # Réinsérer les lignes vides et appliquer les remplacements
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
                        text = self.wrap_text_plain(text, line_width)
                        text_result.append(text)
                        non_empty_idx += 1

            text_output = "\n".join(text_result)
            return text_output
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en texte : {e}")
            return ""

    def ensure_readability(self, braille_text):
        return braille_text

    def __del__(self):
        """Nettoyer le pool de threads à la fermeture."""
        self.executor.shutdown(wait=True)