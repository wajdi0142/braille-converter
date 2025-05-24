import louis
from langdetect import detect
import logging
from backend.config import TABLE_NAMES, TABLES_DIRECTORY
import os
import re

# Constante pour la conversion inverse
LOU_BACKTRANSLATE = 0x0002

class LanguageDetector:
    def __init__(self):
        # Mapper les codes de langue aux noms de tables
        self.language_to_table = {
            'ar': 'Arabe (grade 1)',
            'fr': 'Français (grade 1)',
            'en': 'Anglais (grade 1)'
        }
        
    def detect_language(self, text):
        """Détecte la langue du texte (arabe, français, anglais) avec heuristique, sinon langdetect."""
        try:
            # Heuristique pour l'arabe
            if re.search(r'[\u0600-\u06FF]', text):
                logging.debug("Heuristique : caractères arabes détectés.")
                return 'ar'
            # Heuristique pour le français (lettres accentuées courantes)
            if re.search(r'[éèêëàâäîïôöùûüçœÉÈÊËÀÂÄÎÏÔÖÙÛÜÇŒ]', text):
                logging.debug("Heuristique : caractères français détectés.")
                return 'fr'
            # Sinon, utiliser langdetect (pour l'anglais ou autres)
            lang_code = detect(text)
            logging.debug(f"Langue détectée par langdetect : {lang_code}")
            # On force 'en' si ce n'est ni 'ar' ni 'fr'
            if lang_code not in ('ar', 'fr'):
                return 'en'
            return lang_code
        except Exception as e:
            logging.error(f"Erreur lors de la détection de la langue : {str(e)}")
            return 'en'  # Par défaut, anglais
            
    def get_braille_table(self, lang_code):
        """Retourne le chemin complet de la table braille correspondant à la langue détectée."""
        table_name = self.language_to_table.get(lang_code, 'Anglais (Grade 1)')
        table_file = TABLE_NAMES.get(table_name)
        if table_file:
            return os.path.join(TABLES_DIRECTORY, table_file)
        return None
        
    def convert_to_braille(self, text):
        """Convertit le texte en braille en utilisant la table appropriée."""
        try:
            # Détecter la langue
            lang_code = self.detect_language(text)
            
            # Obtenir la table correspondante
            table_path = self.get_braille_table(lang_code)
            if not table_path:
                logging.error(f"Aucune table trouvée pour la langue {lang_code}")
                return None
            
            # Convertir en braille
            braille = louis.translateString([table_path], text)
            
            logging.debug(f"Conversion réussie : {text[:50]}... -> {braille[:50]}...")
            return braille
            
        except Exception as e:
            logging.error(f"Erreur lors de la conversion en braille : {str(e)}")
            return None
            
    def convert_from_braille(self, braille_text, lang_code='ar'):
        """Convertit le braille en texte en utilisant la table appropriée."""
        try:
            # Obtenir la table correspondante
            table_path = self.get_braille_table(lang_code)
            if not table_path:
                logging.error(f"Aucune table trouvée pour la langue {lang_code}")
                return None
            
            # Convertir depuis le braille
            text = louis.translateString([table_path], braille_text, mode=LOU_BACKTRANSLATE)
            
            logging.debug(f"Conversion inverse réussie : {braille_text[:50]}... -> {text[:50]}...")
            return text
            
        except Exception as e:
            logging.error(f"Erreur lors de la conversion depuis le braille : {str(e)}")
            return None 