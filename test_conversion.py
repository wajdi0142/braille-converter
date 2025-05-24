import unittest
from backend.braille_engine import BrailleEngine
import json
import os

class TestBrailleConversion(unittest.TestCase):
    def setUp(self):
        self.braille_engine = BrailleEngine()
        with open('custom_tables.json', 'r', encoding='utf-8') as f:
            self.custom_tables = json.load(f)
        
        # Obtenir les chemins des tables disponibles
        self.available_tables = self.braille_engine.get_available_tables()
        self.french_table = None
        self.arabic_table = None
        
        for name, path in self.available_tables.items():
            if "fr" in name.lower():
                self.french_table = path
            elif "ar" in name.lower():
                self.arabic_table = path
        
        if not self.french_table or not self.arabic_table:
            raise Exception("Tables de conversion non trouvées")

    def test_french_conversion(self):
        """Test la conversion bidirectionnelle pour le français"""
        test_cases = [
            "Bonjour le monde",
            "À bientôt",
            "Ça va bien",
            "L'été est chaud",
            "Écoute-moi",
            "Ève et Ève",
            "Être ou ne pas être",
            "Noël approche",
            "1234567890",
            ".,;:!?()[]{}",
            "Test avec des caractères spéciaux : éèêëàâôîùçœ"
        ]

        for text in test_cases:
            # Conversion texte vers braille
            braille = self.braille_engine.to_braille(text, self.french_table)
            self.assertIsNotNone(braille, f"La conversion vers braille a échoué pour : {text}")
            
            # Conversion braille vers texte
            text_back = self.braille_engine.from_braille(braille, self.french_table)
            self.assertIsNotNone(text_back, f"La conversion depuis le braille a échoué pour : {braille}")
            
            # Vérification de la correspondance
            self.assertEqual(text.lower(), text_back.lower(), 
                           f"La conversion bidirectionnelle ne correspond pas pour : {text}")

    def test_arabic_conversion(self):
        """Test la conversion bidirectionnelle pour l'arabe"""
        test_cases = [
            "مرحبا بالعالم",
            "كيف حالك",
            "أهلاً وسهلاً",
            "شكراً جزيلاً",
            "مع السلامة",
            "1234567890",
            ".,;:!?()[]{}",
            "Test avec des caractères spéciaux : ًٌٍَُِّْ"
        ]

        for text in test_cases:
            # Conversion texte vers braille
            braille = self.braille_engine.to_braille(text, self.arabic_table)
            self.assertIsNotNone(braille, f"La conversion vers braille a échoué pour : {text}")
            
            # Conversion braille vers texte
            text_back = self.braille_engine.from_braille(braille, self.arabic_table)
            self.assertIsNotNone(text_back, f"La conversion depuis le braille a échoué pour : {braille}")
            
            # Vérification de la correspondance
            self.assertEqual(text, text_back, 
                           f"La conversion bidirectionnelle ne correspond pas pour : {text}")

    def test_custom_tables(self):
        """Test les tables de conversion personnalisées"""
        for lang, table in self.custom_tables.items():
            table_path = None
            for name, path in self.available_tables.items():
                if lang.lower() in name.lower():
                    table_path = path
                    break
            
            if not table_path:
                continue
                
            for char, braille in table.items():
                # Test conversion vers braille
                result = self.braille_engine.to_braille(char, table_path)
                self.assertIsNotNone(result, f"La conversion vers braille a échoué pour {char} en {lang}")
                
                # Test conversion depuis braille
                result = self.braille_engine.from_braille(braille, table_path)
                self.assertIsNotNone(result, f"La conversion depuis le braille a échoué pour {braille} en {lang}")

    def test_paste_braille_in_inverse_mode(self):
        """Simule le collage d'un texte braille dans la zone braille en mode inverse et vérifie la conversion."""
        # Exemple : texte français
        text = "Bonjour"
        # Conversion texte -> braille
        braille = self.braille_engine.to_braille(text, self.french_table)
        # Simuler le collage du braille dans la zone braille (mode inverse)
        # Conversion braille -> texte
        text_back = self.braille_engine.from_braille(braille, self.french_table)
        self.assertIsNotNone(text_back, "La conversion depuis le braille a échoué lors du collage.")
        self.assertEqual(text.lower(), text_back.lower(), "Le texte reconverti ne correspond pas après collage en mode inverse.")

        # Exemple : texte arabe
        text_ar = "مرحبا"
        braille_ar = self.braille_engine.to_braille(text_ar, self.arabic_table)
        text_ar_back = self.braille_engine.from_braille(braille_ar, self.arabic_table)
        self.assertIsNotNone(text_ar_back, "La conversion depuis le braille a échoué lors du collage (arabe).")
        self.assertEqual(text_ar, text_ar_back, "Le texte arabe reconverti ne correspond pas après collage en mode inverse.")

if __name__ == '__main__':
    unittest.main() 