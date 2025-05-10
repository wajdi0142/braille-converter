import os

DB_FOLDER = "db"
DB_NAME = "ma_base_de_donnees.db"
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)

# Configuration des polices
BRAILLE_FONT_NAME = "Noto Sans Braille"
FALLBACK_FONT = "Arial"
FONT_PATH = os.getenv("FONT_PATH", r"C:\Users\LENOVO\Downloads\Noto_Sans_Symbols_2\NotoSansSymbols2-Regular.ttf")

# Chemins pour LibLouis
LOU_TRANSLATE_PATH = os.getenv("LOU_TRANSLATE_PATH", r"C:\msys64\usr\bin\lou_translate.exe")
TABLES_DIRECTORY = os.getenv("TABLES_DIR", r"C:\msys64\usr\share\liblouis\tables")

# Tables de conversion harmonisées
TABLE_NAMES = {
    "Arabe (Grade 1)": "ar-ar-g1.utb",  # Arabe grade 1
    "Français (Grade 1)": "fr-bfu-comp6.utb",  # Français grade 1
    "Français (Grade 2)": "fr-bfu-g2.ctb",  # Français grade 2
    "Anglais (Grade 1)": "en-us-g1.ctb",  # Anglais grade 1
    "Anglais (Grade 2)": "en-us-g2.ctb",  # Anglais grade 2
}