import subprocess
import os
import unicodedata
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from backend.config import LOU_TRANSLATE_PATH, TABLES_DIRECTORY

class BrailleEngine:
    def __init__(self, lou_path=LOU_TRANSLATE_PATH, tables_dir=TABLES_DIRECTORY):
        self.lou_path = self._check_liblouis(lou_path)
        self.tables_dir = tables_dir
        self.custom_table = {}
        self.load_custom_table()

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

    def get_available_tables(self):
        all_tables = [f for f in os.listdir(self.tables_dir) if f.endswith((".utb", ".ctb"))]
        table_names = {
            "Arabe (grade 1)": "ar-ar-g1.utb",
            "Français (grade 1)": "fr-bfu-comp6.utb",  # Corrigé pour grade 1
            "Français (grade 2)": "fr-bfu-g2.ctb",
            "Anglais (grade 1)": "en-us-g1.ctb",
            "Anglais (grade 2)": "en-us-g2.ctb",
        }
        return {name: os.path.join(self.tables_dir, filename) for name, filename in table_names.items() if filename in all_tables}

    def wrap_text(self, text, width=40):
        lines = text.split("\n")
        wrapped_lines = []
        for line in lines:
            current_line = ""
            for char in line:
                if char in self.custom_table:
                    braille_seq = self.custom_table[char]
                    if len(current_line) + len(braille_seq) > width:
                        wrapped_lines.append(current_line.rstrip())
                        current_line = braille_seq
                    else:
                        current_line += braille_seq
                else:
                    if len(current_line) + 1 > width:
                        wrapped_lines.append(current_line.rstrip())
                        current_line = char
                    else:
                        current_line += char
            wrapped_lines.append(current_line.rstrip())
        return "\n".join(wrapped_lines)

    def to_braille(self, text, table_path, line_width=40, capitalize=False, section_separator="\u28CD"):
        if not self.lou_path or not text:
            return ""
        try:
            # Normalisation UTF-8 NFC pour caractères accentués
            text = unicodedata.normalize("NFC", text)

            # Appliquer les caractères personnalisés avant LibLouis
            for char, braille in self.custom_table.items():
                text = text.replace(char, braille)

            cmd = [self.lou_path, "--forward", table_path]
            if capitalize:
                cmd.append("--caps-mode=uc")
            cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
            result = subprocess.run(
                cmd,
                input=text,
                text=True,
                capture_output=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            if result.stderr:
                raise Exception(result.stderr)
            braille_output = result.stdout.strip()

            braille_output = self.ensure_readability(braille_output)
            if section_separator:
                braille_output = braille_output.replace("\n\n", f"\n{section_separator}\n")
            braille_output = self.wrap_text(braille_output, line_width)
            return braille_output
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en braille : {e}")
            return ""

    def ensure_readability(self, braille_text):
        return braille_text  # Peut être amélioré si besoin

    def from_braille(self, braille_text, table_path):
        if not self.lou_path or not braille_text:
            return ""
        try:
            cmd = [self.lou_path, "--backward", table_path]
            cmd.extend(["--display-table", os.path.join(self.tables_dir, "unicode.dis")])
            result = subprocess.run(
                cmd,
                input=braille_text,
                text=True,
                capture_output=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            )
            if result.stderr:
                raise Exception(result.stderr)
            text = result.stdout.strip()
            for char, braille in self.custom_table.items():
                text = text.replace(braille, char)
            return text
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en texte : {e}")
            return ""