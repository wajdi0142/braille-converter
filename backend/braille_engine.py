import subprocess
import os
from PyQt5.QtWidgets import QMessageBox, QFileDialog

class BrailleEngine:
    def __init__(self, lou_path="C:\\msys64\\usr\\bin\\lou_translate.exe", tables_dir="C:\\msys64\\usr\\share\\liblouis\\tables"):
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
                        if len(char) == 1 and all('\u2800' <= c <= '\u28FF' for c in braille):
                            self.custom_table[char] = braille
                    except ValueError:
                        print(f"Format incorrect dans {custom_file} : {line.strip()}")

    def get_available_tables(self):
        all_tables = [f for f in os.listdir(self.tables_dir) if f.endswith((".utb", ".ctb"))]
        table_names = {
            "Français (grade 1)": "fr-bfu-comp6.utb",
            "Français (grade 2)": "fr-bfu-comp8.utb",
            "English (grade 1)": "en-us-g1.ctb",
            "English (grade 2)": "en-us-g2.ctb",
            "Arabe (grade 1)": "ar-ar-g1.utb",
        }
        return {name: os.path.join(self.tables_dir, filename) for name, filename in table_names.items() if filename in all_tables}

    def wrap_text(self, text, width=40):
        lines = []
        current_line = ""
        i = 0
        while i < len(text):
            if i + 1 < len(text) and '\u2800' <= text[i] <= '\u28FF' and '\u2800' <= text[i + 1] <= '\u28FF':
                pair = text[i:i+2]
                if len(current_line) + 2 > width:
                    lines.append(current_line.rstrip())
                    current_line = pair
                else:
                    current_line += pair
                i += 2
            else:
                if len(current_line) + 1 > width:
                    lines.append(current_line.rstrip())
                    current_line = text[i]
                else:
                    current_line += text[i]
                i += 1
        if current_line:
            lines.append(current_line.rstrip())
        return "\n".join(lines)

    def to_braille(self, text, table_path, line_width=40, capitalize=False, section_separator="\u28CD"):
        if not self.lou_path or not text:
            return ""
        try:
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
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            if result.stderr:
                raise Exception(result.stderr)
            braille_output = result.stdout.strip()
            if section_separator:
                braille_output = braille_output.replace("\n\n", f"\n{section_separator}\n")
            braille_output = self.wrap_text(braille_output, line_width)
            return braille_output
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en braille : {e}")
            return ""

    def from_braille(self, braille_text, table_path):
        if not self.lou_path or not braille_text:
            return ""
        try:
            result = subprocess.run(
                [self.lou_path, "--backward", table_path, "--display-table", os.path.join(self.tables_dir, "unicode.dis")],
                input=braille_text,
                text=True,
                capture_output=True,
                encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW
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