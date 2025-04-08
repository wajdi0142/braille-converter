import subprocess
import os
from PyQt5.QtWidgets import QMessageBox, QFileDialog
from .config import LOU_TRANSLATE_PATH, TABLES_DIRECTORY, TABLE_NAMES

class BrailleEngine:
    def __init__(self):
        self.lou_path = self._check_liblouis()
        self.custom_table = {}

    def _check_liblouis(self):
        if os.path.exists(LOU_TRANSLATE_PATH):
            try:
                result = subprocess.run([LOU_TRANSLATE_PATH, "--version"], capture_output=True, text=True)
                if "Liblouis" in result.stdout:
                    return LOU_TRANSLATE_PATH
            except subprocess.SubprocessError:
                pass
        QMessageBox.warning(None, "Avertissement", "LibLouis non détecté à C:\\msys64\\usr\\bin. Sélectionnez lou_translate.exe.")
        path, _ = QFileDialog.getOpenFileName(None, "Sélectionner lou_translate.exe", "", "Exécutables (*.exe)")
        if path and os.path.exists(path):
            return os.path.normpath(path)
        QMessageBox.critical(None, "Erreur", "Chemin LibLouis invalide. Fermeture.")
        import sys
        sys.exit(1)

    def wrap_text(self, text, width=40):
        lines = []
        current_line = ""
        for char in text:
            if len(current_line) >= width:
                lines.append(current_line)
                current_line = char
            else:
                current_line += char
        if current_line:
            lines.append(current_line)
        return "\n".join(lines)

    def get_available_tables(self):
        all_tables = [os.path.join(TABLES_DIRECTORY, f) for f in os.listdir(TABLES_DIRECTORY) if f.endswith((".utb", ".ctb"))]
        available_tables = {}
        for name, filename in TABLE_NAMES.items():
            if any(filename in table for table in all_tables):
                available_tables[name] = os.path.join(TABLES_DIRECTORY, filename)
        return available_tables

    def to_braille(self, text, table_path, line_width=40):
        if not self.lou_path or not text:
            return ""
        try:
            # Appliquer les personnalisations avant conversion
            for char, braille in self.custom_table.items():
                text = text.replace(char, braille)
            result = subprocess.run(
                [self.lou_path, "--forward", table_path, "--display-table", os.path.normpath(r"C:\msys64\usr\share\liblouis\tables\unicode.dis")],
                input=text, text=True, capture_output=True, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            return self.wrap_text(result.stdout.strip(), line_width)
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en braille : {e}")
            return ""

    def from_braille(self, braille_text, table_path):
        if not self.lou_path or not braille_text:
            return ""
        try:
            result = subprocess.run(
                [self.lou_path, "--backward", table_path, "--display-table", os.path.normpath(r"C:\msys64\usr\share\liblouis\tables\unicode.dis")],
                input=braille_text, text=True, capture_output=True, encoding="utf-8",
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            text = result.stdout.strip()
            # Inverser les personnalisations
            for char, braille in self.custom_table.items():
                text = text.replace(braille, char)
            return text
        except Exception as e:
            QMessageBox.warning(None, "Erreur", f"Erreur de conversion en texte : {e}")
            return ""

    def update_custom_table(self):
        self.custom_table.clear()
        if os.path.exists("custom_table.txt"):
            with open("custom_table.txt", "r", encoding="utf-8") as f:
                for line in f:
                    char, braille = line.strip().split(",")
                    self.custom_table[char] = braille
            print(f"Table personnalisée mise à jour : {self.custom_table}")