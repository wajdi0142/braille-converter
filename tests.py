import unittest
from PyQt5.QtWidgets import QApplication
from frontend.ui import BrailleUI
from backend.braille_engine import BrailleEngine
from backend.database import Database
import sys

app = QApplication(sys.argv)

class TestBrailleConverter(unittest.TestCase):
    def setUp(self):
        self.ui = BrailleUI(app)
        self.engine = BrailleEngine()
        self.db = Database()

    def test_text_to_braille(self):
        text = "Bonjour"
        table = self.ui.available_tables["Français (Grade 1)"]
        braille = self.engine.to_braille(text, table)
        self.assertTrue(len(braille) > 0, "Conversion en Braille échouée")
        self.assertIn("⠃⠕⠝⠚⠕⠥⠗", braille, "Conversion incorrecte")

    def test_braille_to_text(self):
        braille = "⠃⠕⠝⠚⠕⠥⠗"
        table = self.ui.available_tables["Français (Grade 1)"]
        text = self.engine.from_braille(braille, table)
        self.assertEqual(text.lower(), "bonjour", "Conversion inverse incorrecte")

    def test_sync_text_areas(self):
        tab = self.ui.tab_widget.currentWidget()
        tab.text_input.setPlainText("Salut")
        self.ui.sync_text_areas(tab)
        braille = tab.text_output.toPlainText()
        self.assertTrue("⠎⠁⠇⠥⠞" in braille, "Synchronisation texte → Braille échouée")

    def test_database_user(self):
        user_id = self.db.ajouter_utilisateur("Test", "test@example.com", "password")
        user = self.db.get_utilisateur_by_email("test@example.com")
        self.assertEqual(user.nom, "Test", "Ajout utilisateur échoué")
        self.assertEqual(user.email, "test@example.com", "Email incorrect")

    def test_spacing_adjustment(self):
        tab = self.ui.tab_widget.currentWidget()
        tab.text_input.setPlainText("é")
        self.ui.sync_text_areas(tab)
        adjusted_text = tab.text_input.toPlainText()
        self.assertTrue("é " in adjusted_text, "Ajustement d’espacement échoué")

if __name__ == '__main__':
    unittest.main()