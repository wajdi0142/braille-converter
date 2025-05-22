import os
import re
import sys
import time
import shutil
import logging
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QComboBox, QTabWidget, QFileDialog, QToolBar, QAction, QMessageBox,
    QStatusBar, QSlider, QMenuBar, QMenu, QSpinBox, QInputDialog, QLabel,
    QApplication, QSpacerItem, QSizePolicy, QProgressDialog, QFontComboBox,
    QDialog, QDialogButtonBox
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QTime, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QTextCharFormat, QTextCursor, QTextBlockFormat, QTextImageFormat, QFontMetrics, QTextDocument, QTextOption
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from backend.braille_engine import BrailleEngine
from backend.file_handler import FileHandler
from backend.database import Database
from backend.models import Texte, Fichier, Impression
from backend.config import BRAILLE_FONT_NAME
from backend.translator import Translator
from frontend.auth import AuthWidget
from frontend.styles import set_light_mode, set_dark_mode
from frontend.custom_table import CustomBrailleTableWidget
import pytesseract
from PIL import Image, ImageEnhance

# Configurer la journalisation avec niveau DEBUG pour le débogage
logging.basicConfig(filename='qt_errors.log', level=logging.DEBUG, 
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Désactiver les avertissements Qt inutiles
os.environ["QT_LOGGING_RULES"] = "qt5ct.debug=false"

class StderrToLog:
    def __init__(self):
        self.logger = logging.getLogger()
        
    def write(self, message):
        if message.strip() and "QCssParser" in message:
            self.logger.warning(message.strip())
        else:
            sys.__stderr__.write(message)
            
    def flush(self):
        sys.__stderr__.flush()

# Configuration de Tesseract pour l'OCR
pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
    raise Exception("Tesseract-OCR n'est pas installé ou inaccessible.")

tessdata_dir = os.path.join(os.path.dirname(pytesseract.pytesseract.tesseract_cmd), "tessdata")
required_langs = ["fra", "ara"]
for lang in required_langs:
    if not os.path.exists(os.path.join(tessdata_dir, f"{lang}.traineddata")):
        print(f"Avertissement : Le fichier de langue '{lang}.traineddata' est manquant.")

class BrailleConversionThread(QThread):
    conversion_done = pyqtSignal(object, str, str)
    progress_updated = pyqtSignal(int)

    def __init__(self, braille_engine, text, table, line_width):
        super().__init__()
        self.braille_engine = braille_engine
        self.text = text
        self.table = table
        self.line_width = line_width
        self.full_text = text
        self.limit = 500

    def run(self):
        start_convert = time.time()
        text_to_convert = self.text[:self.limit] if len(self.text) > self.limit else self.text
        formatted_text = self.braille_engine.wrap_text_by_sentence(text_to_convert, self.line_width)
        braille_text = self.braille_engine.to_braille(formatted_text, self.table, self.line_width)
        formatted_braille = self.braille_engine.wrap_text_by_sentence(braille_text, self.line_width)
        
        self.progress_updated.emit(50)
        if len(self.text) > self.limit:
            formatted_text += "\n[... Texte tronqué, conversion en cours...]"
            formatted_braille += "\n[... Braille tronqué, conversion en cours...]"
        
        convert_time = time.time() - start_convert
        logging.debug(f"Temps de conversion initiale en Braille: {convert_time:.2f} secondes")
        self.conversion_done.emit(self, formatted_text, formatted_braille)
        
        if len(self.text) > self.limit:
            start_full_convert = time.time()
            full_formatted_text = self.braille_engine.wrap_text_by_sentence(self.full_text, self.line_width)
            full_braille_text = self.braille_engine.to_braille(full_formatted_text, self.table, self.line_width)
            full_formatted_braille = self.braille_engine.wrap_text_by_sentence(full_braille_text, self.line_width)
            self.progress_updated.emit(100)
            full_convert_time = time.time() - start_full_convert
            logging.debug(f"Temps de conversion complète en Braille: {full_convert_time:.2f} secondes")
            self.conversion_done.emit(self, full_formatted_text, full_formatted_braille)

class BrailleTab(QWidget):
    def __init__(self, parent, file_path=None, save_type="Texte + Braille"):
        super().__init__()
        self.parent = parent
        self.file_path = file_path
        self.save_type = save_type
        self.original_text = ""
        self.original_braille = ""
        self.is_updating = False
        self._conversion_thread = None
        self.pending_changes = []
        self.last_modified_lines = set()
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        
        # Créer un layout vertical pour la zone de texte d'entrée
        input_layout = QVBoxLayout()
        self.text_input_label = QLabel("Texte :")
        self.text_input = QTextEdit()
        self.text_input.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        input_layout.addWidget(self.text_input_label)
        input_layout.addWidget(self.text_input)
        
        # Créer un layout vertical pour la zone de texte de sortie
        output_layout = QVBoxLayout()
        self.text_output_label = QLabel("Braille :")
        self.text_output = QTextEdit()
        self.text_output.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        output_layout.addWidget(self.text_output_label)
        output_layout.addWidget(self.text_output)
        
        # Ajouter les layouts à la mise en page principale
        layout.addLayout(input_layout)
        layout.addLayout(output_layout)

    def connect_text_changed(self):
        self.text_input.textChanged.connect(self.parent.on_text_changed)
        self.text_output.textChanged.connect(self.parent.on_text_changed)

    def queue_manual_edit(self, cursor_pos, new_text):
        self.pending_changes.append((cursor_pos, new_text))

    def process_pending_changes(self):
        if not self.pending_changes:
            return

        cursor = self.text_input.textCursor()
        for cursor_pos, new_text in self.pending_changes:
            cursor.setPosition(cursor_pos)
            cursor.insertText(new_text)
        self.pending_changes.clear()
        self.text_input.setTextCursor(cursor)

class TranslationDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Traduction")
        self.setModal(True)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Langue source
        source_layout = QHBoxLayout()
        source_layout.addWidget(QLabel("Langue source :"))
        self.source_lang = QComboBox()
        self.source_lang.addItems(self.parent().translator.get_supported_languages())
        source_layout.addWidget(self.source_lang)
        layout.addLayout(source_layout)

        # Langue cible
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Langue cible :"))
        self.target_lang = QComboBox()
        self.target_lang.addItems(self.parent().translator.get_supported_languages())
        self.target_lang.setCurrentText("Français")  # Langue cible par défaut
        target_layout.addWidget(self.target_lang)
        layout.addLayout(target_layout)

        # Boutons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

class BrailleUI(QMainWindow):
    def __init__(self, app):
        super().__init__()
        logging.debug("BrailleUI instancié")
        self.app = app
        self.setWindowTitle("Convertisseur Texte ↔ Braille")
        self.setGeometry(200, 200, 1350, 800)
        self.initial_size = QSize(1000, 600)

        self.braille_engine = BrailleEngine()
        self.file_handler = FileHandler()
        self.file_handler.parent = self
        self.db = Database()
        self.translator = Translator()
        self.available_tables = self.braille_engine.get_available_tables()

        self.dark_mode = False
        self.min_line_width = 5
        self.line_width = 33  # Valeur par défaut initiale
        self.lines_per_page = 29
        self.line_spacing = 1.0
        self.indent = 0
        self.current_font = BRAILLE_FONT_NAME
        self.base_font_size = 18
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize)
        self.is_typing = False
        self.logged_in_user = None
        self.current_email = None
        self.usage_timer = QTimer()
        self.usage_timer.timeout.connect(self.update_usage_time)
        self.usage_timer.start(1000)
        self.conversion_mode = "text_to_braille"  # Mode de conversion par défaut

        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.process_debounced_conversion)
        self.debounce_delay = 100

        # Attributs pour la saisie Braille directe
        self.braille_points_pressed = set()
        self.braille_key_map = {
            Qt.Key_F: 1,
            Qt.Key_D: 2,
            Qt.Key_S: 3,
            Qt.Key_J: 4,
            Qt.Key_K: 5,
            Qt.Key_L: 6,
            Qt.Key_E: 7, # Généralement point 7
            Qt.Key_I: 8  # Généralement point 8
        }
        self.braille_typing_timer = QTimer()
        self.braille_typing_timer.setSingleShot(True)
        self.braille_typing_timer.timeout.connect(self.finalize_braille_cell)
        self.braille_typing_delay = 300 # Délai en ms pour finaliser la cellule

        self.init_ui()
        
        # Calculer la largeur initiale après l'initialisation de l'interface
        # QTimer.singleShot(100, self.calculate_initial_line_width)
        
        # Appliquer la largeur de ligne initiale par défaut (33)
        QTimer.singleShot(150, lambda: self.apply_line_width_to_tab(self.tab_widget.currentWidget()))

    def calculate_initial_line_width(self):
        """Calcule la largeur de ligne initiale en fonction de la taille de la fenêtre."""
        tab = self.tab_widget.currentWidget()
        if tab:
            try:
                # Calculer la largeur pour les deux zones
                font_metrics_input = QFontMetrics(tab.text_input.font())
                font_metrics_output = QFontMetrics(tab.text_output.font())
                char_width_input = font_metrics_input.averageCharWidth()
                char_width_output = font_metrics_output.averageCharWidth()
                scale = self.zoom_slider.value() / 100.0
                
                # Utiliser la plus petite largeur disponible pour les deux zones
                available_width_input = tab.text_input.viewport().width()
                available_width_output = tab.text_output.viewport().width()
                available_width = min(available_width_input, available_width_output)
                
                # Calculer la largeur en utilisant la plus grande largeur de caractère
                char_width = max(char_width_input, char_width_output)
                new_width = max(self.min_line_width, int(available_width / (char_width * scale)))
                
                if new_width != self.line_width:
                    self.line_width = new_width
                    self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")
                    
                    # Configurer le retour à la ligne pour les deux zones
                    self.apply_line_width_to_tab(tab)
                    
                    self.update_conversion()
            except Exception as e:
                logging.error(f"Erreur lors du calcul de la largeur initiale : {str(e)}")
                self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")

    def apply_line_width_to_tab(self, tab):
        """Applique la largeur de ligne aux deux zones de texte et configure le retour à la ligne."""
        if not tab:
            return

        # Configurer le retour à la ligne pour la zone de texte en utilisant la largeur fixe
        tab.text_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
        tab.text_input.setLineWrapColumnOrWidth(self.line_width)
        tab.text_input.setWordWrapMode(QTextOption.WordWrap)  # Activer le wrapping des mots

        # Configurer le retour à la ligne pour la zone braille en utilisant la largeur fixe
        tab.text_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
        tab.text_output.setLineWrapColumnOrWidth(self.line_width)
        tab.text_output.setWordWrapMode(QTextOption.WordWrap)  # Activer le wrapping des mots

        # Retirer la définition de la largeur minimale pour laisser les widgets s'adapter au layout
        # self.line_width sera utilisé par la logique de formatage du texte avant la conversion
        # tab.text_input.setMinimumWidth(0) # On ne force plus de largeur minimale
        # tab.text_output.setMinimumWidth(0) # On ne force plus de largeur minimale

        # Le formatage du texte basé sur self.line_width est géré par BrailleEngine.wrap_text_by_sentence
        # dans les méthodes de conversion et de mise à jour. Il n'est pas nécessaire de re-formater ici
        # sauf si l'on voulait forcer un re-rendu visuel, ce que WidgetWidth gère.

        # Mettre à jour le braille si le texte d'entrée n'est pas vide pour s'assurer que
        # la conversion utilise la self.line_width calculée.
        if tab.text_input.toPlainText().strip():
             self.update_conversion()

    def update_line_width(self):
        """Calcule et applique la largeur de ligne aux zones de texte."""
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        try:
            # Calculer la nouvelle largeur
            font_metrics_input = QFontMetrics(tab.text_input.font())
            font_metrics_output = QFontMetrics(tab.text_output.font())
            char_width_input = font_metrics_input.averageCharWidth()
            char_width_output = font_metrics_output.averageCharWidth()
            scale = self.zoom_slider.value() / 100.0

            # Utiliser la plus petite largeur disponible pour les deux zones
            # Ajouter une petite marge pour éviter les problèmes d'arrondi ou de scrollbar
            available_width_input = tab.text_input.viewport().width() - 20 # Marge de 20 pixels
            available_width_output = tab.text_output.viewport().width() - 20 # Marge de 20 pixels
            available_width = min(available_width_input, available_width_output)
            available_width = max(1, available_width) # Assurer une largeur minimale de 1

            # Calculer la largeur en utilisant la plus grande largeur de caractère
            char_width = max(char_width_input, char_width_output)
            
            # Éviter la division par zéro et les largeurs négatives ou nulles
            if char_width <= 0 or scale <= 0:
                new_width = self.min_line_width
            else:
                new_width = max(self.min_line_width, int(available_width / (char_width * scale)))
            
            # Limiter la largeur maximale à une valeur raisonnable pour éviter les géométries excessives
            max_reasonable_width = 200 # Par exemple, limiter à 200 caractères
            new_width = min(new_width, max_reasonable_width)


            if new_width != self.line_width:
                self.line_width = new_width
                self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")

                # Appliquer la nouvelle largeur aux deux zones
                self.apply_line_width_to_tab(tab)

                self.status_bar.showMessage(f"Largeur des lignes ajustée à {self.line_width} caractères", 3000)

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de la largeur : {str(e)}")
            self.status_bar.showMessage("Erreur lors de l'ajustement de la largeur", 3000)

    def init_ui(self):
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.stack_layout = QVBoxLayout(self.central_widget)

        self.auth_container = QWidget()
        self.auth_layout = QVBoxLayout(self.auth_container)
        self.auth_layout.setAlignment(Qt.AlignCenter)
        self.auth_widget = AuthWidget(self)
        self.auth_widget.logout_signal.connect(self.handle_logout)

        auth_inner_layout = QHBoxLayout()
        auth_inner_layout.addStretch()
        auth_inner_layout.addWidget(self.auth_widget)
        auth_inner_layout.addStretch()
        self.auth_layout.addLayout(auth_inner_layout)
        self.stack_layout.addWidget(self.auth_container)
        self.auth_container.hide()

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.title_label = QLabel("Convertisseur Texte ↔ Braille")
        self.title_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.main_layout.addWidget(self.title_label)

        table_layout = QHBoxLayout()
        self.table_combo_label = QLabel("Langue (Table) :")
        self.table_combo = QComboBox()
        self.table_combo.addItems(self.available_tables.keys())
        self.table_combo.setCurrentText("Français (grade 1)")
        self.table_combo.currentTextChanged.connect(self.update_conversion)
        table_layout.addWidget(self.table_combo_label)
        table_layout.addWidget(self.table_combo)
        
        self.line_width_label = QLabel(f"Largeur de ligne : {self.line_width} caractères")
        table_layout.addStretch()
        self.main_layout.addLayout(table_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.main_layout.addWidget(self.tab_widget)

        control_layout = QHBoxLayout()
        counters_layout = QHBoxLayout()
        self.page_count_label = QLabel("Page :")
        self.page_count = QLabel("1")
        self.line_count_label = QLabel(" | Ligne :")
        self.line_count = QLabel("0")
        self.word_count_label = QLabel(" | Mots :")
        self.word_count = QLabel("0")
        counters_layout.addWidget(self.page_count_label)
        counters_layout.addWidget(self.page_count)
        counters_layout.addWidget(self.line_count_label)
        counters_layout.addWidget(self.line_count)
        counters_layout.addWidget(self.word_count_label)
        counters_layout.addWidget(self.word_count)
        control_layout.addLayout(counters_layout)

        zoom_layout = QHBoxLayout()
        self.zoom_label = QLabel("Zoom: 100%")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(50)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setSingleStep(1)
        self.zoom_slider.setTickPosition(QSlider.TicksBelow)
        self.zoom_slider.setTickInterval(10)
        self.zoom_slider.valueChanged.connect(self.apply_zoom)
        self.zoom_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #B1B1B1, stop:1 #E0E0E0);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #AAAAAA);
                border: 1px solid #5c5c5c;
                width: 18px;
                margin: -2px 0;
                border-radius: 9px;
            }
            QSlider::handle:horizontal:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #FFFFFF, stop:1 #CCCCCC);
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #66BB6A, stop:1 #4CAF50);
                border-radius: 4px;
            }
        """)
        self.reset_zoom_button = QPushButton("Réinitialiser Zoom")
        self.reset_zoom_button.clicked.connect(self.reset_zoom)
        self.toggle_size_button = QPushButton()
        self.toggle_size_button.setIcon(self.safe_icon("icons/maximize.png"))
        self.toggle_size_button.clicked.connect(self.toggle_window_size)
        zoom_layout.addStretch()
        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.reset_zoom_button)
        zoom_layout.addWidget(self.toggle_size_button)
        control_layout.addLayout(zoom_layout)
        self.main_layout.addLayout(control_layout)

        # Label pour afficher le temps d'utilisation
        self.usage_time_label = QLabel("Temps d'utilisation : --:--:--")
        
        self.init_status_bar()

        self.stack_layout.addWidget(self.main_widget)
        self.main_widget.show()
        self.new_document()

        self.init_menu_bar()
        self.toolbar = self.addToolBar("Main Toolbar")
        self.init_toolbar()

        set_light_mode(self.app)
        self.auth_widget.check_device_auth()

    def safe_icon(self, path):
        return QIcon(path) if os.path.exists(path) else QIcon()

    def toggle_auth_interface(self):
        was_maximized = self.isMaximized()
        current_size = self.size()

        if self.main_widget.isVisible():
            self.main_widget.hide()
            self.auth_container.show()
            self.status_bar.showMessage("Espace d'authentification")
        else:
            self.auth_container.hide()
            self.main_widget.show()
            self.status_bar.showMessage("Retour à l'interface principale")

        if was_maximized:
            self.showMaximized()
        else:
            self.resize(current_size)

    def show_main_interface(self, email, user_info):
        self.logged_in_user = self.db.get_utilisateur_by_email(email)
        if not self.logged_in_user:
            user_id = self.db.ajouter_utilisateur(user_info.get("nom", email.split("@")[0]), email)
            self.logged_in_user = self.db.get_utilisateur_by_email(email)
        self.current_email = email
        self.auth_container.hide()
        self.main_widget.show()
        self.auth_button.setIcon(self.safe_icon("icons/user-logged-in.png"))
        self.auth_button.setText(f"{email}")
        self.auth_button.setToolTip(f"Connecté : {email}")
        self.usage_start_time = QTime.currentTime()

        if self.was_maximized:
            self.showMaximized()
        else:
            self.resize(self.current_size)

    def handle_logout(self):
        self.was_maximized = self.isMaximized()
        self.current_size = self.size()

        if self.logged_in_user:
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        self.logged_in_user = None
        self.current_email = None
        self.auth_widget.logged_in_event()
        self.auth_button.setIcon(self.safe_icon("icons/user.png"))
        self.auth_button.setText("Se connecter")
        self.auth_button.setToolTip("Se connecter")
        self.status_bar.showMessage("Espace d'authentification")

        if self.was_maximized:
            self.showMaximized()
        else:
            self.resize(self.current_size)

    def init_menu_bar(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("Fichier")
        new_action = QAction("Nouveau", self)
        new_action.setShortcut("Ctrl+N")
        new_action.triggered.connect(self.new_document)
        file_menu.addAction(new_action)

        # Ajouter l'action de test des styles
        test_styles_action = QAction("Tester les styles PDF", self)
        test_styles_action.triggered.connect(self.test_pdf_styles)
        file_menu.addAction(test_styles_action)

        open_action = QAction("Ouvrir", self)
        open_action.setShortcut("Ctrl+O")
        open_action.triggered.connect(self.import_files)
        file_menu.addAction(open_action)

        save_action = QAction("Sauvegarder", self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self.save_document)
        file_menu.addAction(save_action)

        save_as_action = QAction("Enregistrer sous", self)
        save_as_action.triggered.connect(self.save_document_as)
        file_menu.addAction(save_as_action)

        save_braille_action = QAction("Sauvegarder le Braille", self)
        save_braille_action.triggered.connect(self.save_braille_text)
        file_menu.addAction(save_braille_action)

        pdf_action = QAction("Exporter en PDF", self)
        pdf_action.triggered.connect(self.export_to_pdf)
        file_menu.addAction(pdf_action)

        word_action = QAction("Exporter en Word", self)
        word_action.triggered.connect(self.export_to_word)
        file_menu.addAction(word_action)

        gcode_action = QAction("Exporter en Gcode", self)
        gcode_action.triggered.connect(self.export_to_gcode)
        file_menu.addAction(gcode_action)

        image_action = QAction("Ouvrir une image", self)
        image_action.triggered.connect(self.import_image)
        file_menu.addAction(image_action)

        preview_menu = menu_bar.addMenu("Aperçu")
        print_action = QAction("Imprimer Braille", self)
        print_action.setShortcut("Ctrl+P")
        print_action.triggered.connect(self.print_braille)
        preview_menu.addAction(print_action)

        settings_menu = menu_bar.addMenu("Paramètres")
        dark_mode_action = QAction("Activer/Désactiver le mode sombre", self)
        dark_mode_action.triggered.connect(self.toggle_dark_mode)
        settings_menu.addAction(dark_mode_action)
        
        # Ajouter les actions de paramètres avec des QAction
        line_width_action = QAction("Ajuster la largeur des lignes", self)
        line_width_action.triggered.connect(self.adjust_line_width)
        settings_menu.addAction(line_width_action)
        
        lines_per_page_action = QAction("Ajuster le nombre de lignes par page", self)
        lines_per_page_action.triggered.connect(self.adjust_lines_per_page)
        settings_menu.addAction(lines_per_page_action)
        
        line_spacing_action = QAction("Ajuster l'interligne", self)
        line_spacing_action.triggered.connect(self.adjust_line_spacing)
        settings_menu.addAction(line_spacing_action)
        
        indent_action = QAction("Ajuster le retrait", self)
        indent_action.triggered.connect(self.adjust_indent)
        settings_menu.addAction(indent_action)
        
        custom_table_action = QAction("Personnaliser table Braille", self)
        custom_table_action.triggered.connect(self.show_custom_table)
        settings_menu.addAction(custom_table_action)
        
        stats_action = QAction("Voir les statistiques d'utilisation", self)
        stats_action.triggered.connect(self.show_usage_stats)
        settings_menu.addAction(stats_action)
        
        test_action = QAction("Tester la conversion", self)
        test_action.triggered.connect(self.test_conversion)
        settings_menu.addAction(test_action)

        edit_menu = menu_bar.addMenu("Édition")
        edit_menu.addAction("Effacer le texte", self.clear_text)

        translate_action = QAction("Traduire en Braille", self)
        translate_action.setShortcut("Ctrl+T")
        translate_action.triggered.connect(self.update_conversion)
        edit_menu.addAction(translate_action)

        invert_action = QAction("Inverser Texte/Braille", self)
        invert_action.setShortcut("Ctrl+I")
        invert_action.triggered.connect(self.invert_text)
        edit_menu.addAction(invert_action)

        # Ajouter le menu de traduction
        translate_menu = menu_bar.addMenu("Traduction")
        translate_text_action = QAction("Traduire le texte", self)
        translate_text_action.setShortcut("Ctrl+Shift+T")
        translate_text_action.triggered.connect(self.translate_text)
        translate_menu.addAction(translate_text_action)

        detect_lang_action = QAction("Détecter la langue", self)
        detect_lang_action.triggered.connect(self.detect_language)
        translate_menu.addAction(detect_lang_action)

    def init_toolbar(self):
        icons = [
            ("icons/new.png", "Nouveau", self.new_document, "new_action"),
            ("icons/open.png", "Ouvrir", self.import_files, "open_action"),
            ("icons/image.png", "Ouvrir une image", self.import_image, "image_action"),
            ("icons/save.png", "Sauvegarder", self.save_document, "save_action"),
            ("icons/save_as.png", "Enregistrer sous", self.save_document_as, "save_as_action"),
            ("icons/braille.png", "Sauvegarder le Braille", self.save_braille_text, "save_braille_action"),
            ("icons/pdf.png", "Exporter en PDF", self.export_to_pdf, "pdf_action"),
            ("icons/word.png", "Exporter en Word", self.export_to_word, "word_action"),
            ("icons/braille_print.png", "Imprimer en Braille", self.print_braille, "print_action"),
            ("icons/sun.png", "Mode Sombre", self.toggle_dark_mode, "dark_mode_action"),
            ("icons/reverse.png", "Inverser Texte/Braille", self.invert_text, "invert_action"),
            ("icons/bold.png", "Gras", self.toggle_bold, ""),
            ("icons/italic.png", "Italique", self.toggle_italic, ""),
            ("icons/souligne.png", "Souligné", self.toggle_underline, ""),
            ("icons/align-left.png", "Aligner à gauche", lambda: self.align_text(Qt.AlignLeft), ""),
            ("icons/align-center.png", "Aligner au centre", lambda: self.align_text(Qt.AlignCenter), ""),
            ("icons/align-right.png", "Aligner à droite", lambda: self.align_text(Qt.AlignRight), ""),
        ]
        for icon_path, tooltip, callback, attr_name in icons:
            action = self.toolbar.addAction(self.safe_icon(icon_path), tooltip, callback)
            if attr_name:
                setattr(self, attr_name, action)

        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Police : "))
        self.font_combo = QFontComboBox()
        self.font_combo.setCurrentFont(QFont(BRAILLE_FONT_NAME))
        self.font_combo.currentFontChanged.connect(self.change_font)
        self.toolbar.addWidget(self.font_combo)

        self.toolbar.addWidget(QLabel(" Taille : "))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(4)
        self.font_size_spin.setMaximum(64)
        self.font_size_spin.setValue(12)
        self.font_size_spin.valueChanged.connect(self.adjust_font_size)
        self.toolbar.addWidget(self.font_size_spin)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)

        self.auth_button = QPushButton("Se connecter")
        self.auth_button.setIcon(self.safe_icon("icons/user.png"))
        self.auth_button.setToolTip("Se connecter")
        self.auth_button.clicked.connect(self.toggle_auth_interface)
        self.toolbar.addWidget(self.auth_button)

    def init_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        # Ajouter les autres compteurs à droite du temps d'utilisation
        self.status_bar.addPermanentWidget(self.page_count_label)
        self.status_bar.addPermanentWidget(self.page_count)
        self.status_bar.addPermanentWidget(self.line_count_label)
        self.status_bar.addPermanentWidget(self.line_count)
        self.status_bar.addPermanentWidget(self.word_count_label)
        self.status_bar.addPermanentWidget(self.word_count)
        self.status_bar.showMessage("Prêt")

    def change_font(self, font):
        self.current_font = font.family()
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        cursor = tab.text_input.textCursor()
        block_format = cursor.blockFormat()
        current_line_spacing = block_format.lineHeight() / 100 if block_format.lineHeight() else self.line_spacing
        current_indent = block_format.textIndent()
        current_alignment = block_format.alignment()

        scale = self.zoom_slider.value() / 100.0
        font_size = int(self.base_font_size * scale)
        tab.text_input.setFont(QFont(self.current_font, font_size))
        tab.text_output.setFont(QFont(self.current_font, font_size))

        if not cursor.hasSelection():
            cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setFontFamily(self.current_font)
        cursor.mergeCharFormat(fmt)

        block_format.setLineHeight(current_line_spacing * 100, QTextBlockFormat.ProportionalHeight)
        block_format.setTextIndent(current_indent)
        block_format.setAlignment(current_alignment)
        cursor.setBlockFormat(block_format)

        tab.text_input.setTextCursor(cursor)
        self.sync_text_areas(tab)
        self.update_conversion()

    def invert_text(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)
            if self.conversion_mode == "text_to_braille":
                self.conversion_mode = "braille_to_text"
                tab.text_input_label.setText("Braille :")
                tab.text_output_label.setText("Texte :")
                tab.text_input.setPlainText(tab.original_braille)
                selected_table = self.table_combo.currentText()
                if tab.original_braille and selected_table:
                    text = self.braille_engine.from_braille(tab.original_braille, self.available_tables[selected_table])
                    tab.text_output.setPlainText(text)
                else:
                    tab.text_output.clear()
            else:
                self.conversion_mode = "text_to_braille"
                tab.text_input_label.setText("Texte :")
                tab.text_output_label.setText("Braille :")
                tab.text_input.setPlainText(tab.original_text)
                tab.text_output.setPlainText(tab.original_braille)
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            self.update_counters()

    def keyPressEvent(self, event):
        # Cette méthode gère les raccourcis globaux au niveau de la fenêtre principale
        # La saisie Braille directe est gérée par l'eventFilter sur la zone de texte Braille
        key = event.key()
        modifiers = event.modifiers()

        # Gérer les raccourcis Ctrl et autres touches spéciales
        if modifiers & Qt.ControlModifier:
            if key == Qt.Key_B:
                self.toggle_bold()
                event.accept()
                return
            elif key == Qt.Key_I:
                if modifiers & Qt.ShiftModifier:
                     self.invert_text()
                else:
                    self.toggle_italic()
                event.accept()
                return
            elif key == Qt.Key_U:
                self.toggle_underline()
                event.accept()
                return
            elif key == Qt.Key_Plus:
                self.zoom_slider.setValue(self.zoom_slider.value() + 1)
                self.apply_zoom()
                event.accept()
                return
            elif key == Qt.Key_Minus:
                self.zoom_slider.setValue(self.zoom_slider.value() - 1)
                self.apply_zoom()
                event.accept()
                return
            elif key == Qt.Key_T:
                 if modifiers & Qt.ShiftModifier:
                      self.translate_text()
                      event.accept() # Accepter si la traduction est déclenchée
                      return
                 # Ctrl+T sans Shift n'a pas de comportement spécifique immédiat ici.
                 # Il sera géré par le comportement par défaut si non intercepté ailleurs.

        # Gérer les touches de fonction comme F11
        if key == Qt.Key_F11:
            self.toggle_fullscreen()
            event.accept()
            return

        # Pour toutes les autres touches non gérées ici, laisser la propagation par défaut.
        # Si le focus est sur un QTextEdit, celui-ci gérera la saisie ou le déplacement du curseur.
        super().keyPressEvent(event)

    # Nouvelle méthode eventFilter pour gérer les événements de widgets spécifiques
    def eventFilter(self, obj, event):
        # Vérifier si l'événement est une pression de touche et si l'objet est la zone de texte Braille
        tab = self.tab_widget.currentWidget()
        if tab and obj == tab.text_input and event.type() == QEvent.KeyPress:
            key = event.key()
            modifiers = event.modifiers()

            # Si le mode de conversion est braille_to_text
            if self.conversion_mode == "braille_to_text":
                # Gérer les touches correspondant aux points Braille
                if key in self.braille_key_map:
                    point = self.braille_key_map[key]
                    self.braille_points_pressed.add(point)
                    self.braille_typing_timer.start(self.braille_typing_delay)
                    event.accept() # Accepter l'événement pour empêcher la saisie normale
                    return True # Indiquer que l'événement a été géré
                # Gérer les touches de finalisation de cellule ou de navigation
                elif key in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
                    self.finalize_braille_cell() # Finaliser la cellule actuelle
                    # Retourner False pour permettre au QTextEdit d'insérer l'espace/saut de ligne
                    return False
                elif key == Qt.Key_Backspace:
                    self.finalize_braille_cell() # Finaliser avant de supprimer
                    # Retourner False pour permettre au QTextEdit de gérer la suppression
                    return False
                elif key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
                    self.finalize_braille_cell() # Finaliser avant de déplacer le curseur
                    # Retourner False pour permettre au QTextEdit de déplacer le curseur
                    return False
                else:
                    # Si une autre touche est pressée en mode Braille (non point, non finalisation, non flèche)
                    # finaliser la cellule et bloquer la saisie normale.
                    self.finalize_braille_cell()
                    event.accept() # Assurer que le caractère n'est pas saisi
                    return True # Indiquer que l'événement a été géré

        # Pour tous les autres objets ou événements non gérés ici, passer à la classe parente (comportement par défaut)
        return super().eventFilter(obj, event)

    def finalize_braille_cell(self):
        if not self.braille_points_pressed:
            return

        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        # Calculer la valeur Unicode de la cellule Braille
        braille_value = 0x2800 # Code Unicode de la cellule Braille vide
        for point in sorted(list(self.braille_points_pressed)): # Trier les points pour une valeur cohérente
            if 1 <= point <= 8:
                braille_value |= (1 << (point - 1))

        braille_char = chr(braille_value)

        # Insérer le caractère Braille dans la zone de texte Braille
        cursor = tab.text_input.textCursor()
        cursor.insertText(braille_char)

        # Effacer les points pressés pour la prochaine cellule
        self.braille_points_pressed.clear()

        # update_conversion est déjà appelée par le signal textChanged du QTextEdit
        # self.update_conversion()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.toggle_size_button.setIcon(self.safe_icon("icons/maximize.png"))
        else:
            self.showFullScreen()
            self.toggle_size_button.setIcon(self.safe_icon("icons/restore.png"))
        self.update_line_width()
        self.update_conversion()

    def toggle_bold(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setFontWeight(QFont.Bold if not cursor.charFormat().fontWeight() == QFont.Bold else QFont.Normal)
        cursor.mergeCharFormat(fmt)
        self.sync_text_areas(tab)
        self.update_counters()

    def toggle_italic(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setFontItalic(not cursor.charFormat().fontItalic())
        cursor.mergeCharFormat(fmt)
        self.sync_text_areas(tab)
        self.update_counters()

    def toggle_underline(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        if not cursor.hasSelection():
            return
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
        cursor.mergeCharFormat(fmt)
        self.sync_text_areas(tab)
        self.update_counters()

    def apply_zoom(self, value):
        """Met à jour le niveau de zoom pour les deux zones de texte et préserve les formats."""
        try:
            current_tab = self.tab_widget.currentWidget()
            if not current_tab:
                return

            text_input = current_tab.text_input
            braille_output = current_tab.text_output

            if not text_input or not braille_output:
                return

            # Sauvegarder le texte et les styles (partie conservée si nécessaire)
            text_cursor = text_input.textCursor()
            text_has_selection = text_cursor.hasSelection()
            text_start = text_cursor.selectionStart() if text_has_selection else text_cursor.position()
            text_end = text_cursor.selectionEnd() if text_has_selection else text_cursor.position()

            braille_cursor = braille_output.textCursor()
            braille_has_selection = braille_cursor.hasSelection()
            braille_start = braille_cursor.selectionStart() if braille_has_selection else braille_cursor.position()
            braille_end = braille_cursor.selectionEnd() if braille_has_selection else braille_cursor.position()

            # Sauvegarder les documents formatés (conservé pour préserver les styles)
            text_document = text_input.document().clone()
            braille_document = braille_output.document().clone()

            # Appliquer le nouveau zoom à la taille de base de la police
            zoom_factor = value / 100.0
            new_font_size = int(self.base_font_size * zoom_factor)

            # Appliquer la nouvelle taille de police aux zones de texte temporairement
            temp_font_input = QFont(self.current_font, new_font_size)
            temp_font_output = QFont(self.current_font, new_font_size)

            # Ne pas recalculer la largeur de ligne ici, utiliser celle définie par l'utilisateur
            # self.update_line_width() # Cette ligne est supprimée

            # Restaurer les documents formatés (cela réinitialise la police)
            text_input.setDocument(text_document)
            braille_output.setDocument(braille_document)

            # Réappliquer la nouvelle taille de police après la restauration du document
            text_input.setFont(temp_font_input)
            braille_output.setFont(temp_font_output)

            # Restaurer les curseurs et sélections
            text_cursor_restore = text_input.textCursor()
            if text_has_selection:
                text_cursor_restore.setPosition(text_start)
                text_cursor_restore.setPosition(text_end, QTextCursor.KeepAnchor)
            else:
                text_cursor_restore.setPosition(text_start)
            text_input.setTextCursor(text_cursor_restore)

            braille_cursor_restore = braille_output.textCursor()
            if braille_has_selection:
                braille_cursor_restore.setPosition(braille_start)
                braille_cursor_restore.setPosition(braille_end, QTextCursor.KeepAnchor)
            else:
                braille_cursor_restore.setPosition(braille_start)
            braille_output.setTextCursor(braille_cursor_restore)

            # Mettre à jour l'étiquette de zoom
            self.zoom_label.setText(f"Zoom: {value}%")

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour du zoom : {str(e)}")
            QMessageBox.warning(self, "Erreur", f"Erreur lors de la mise à jour du zoom : {str(e)}")

    def adjust_font_size(self):
        font_size = self.font_size_spin.value()
        self.base_font_size = font_size
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        # Vérifier s'il y a une sélection
        if not cursor.hasSelection():
            # Si aucune sélection, ne rien faire pour éviter d'appliquer à tout le document
            # On peut potentiellement mettre à jour la police pour le curseur actuel si l'utilisateur commence à taper
            # mais pour l'instant, on ne modifie que la sélection existante.
            logging.debug("adjust_font_size: No selection, not applying font size.")
            return
        
        # Si une sélection existe, appliquer le formatage uniquement à la sélection
        fmt = QTextCharFormat()
        fmt.setFontPointSize(font_size)
        # Optionnel: Préserver la famille de police existante si ce n'est pas la police Braille par défaut
        # if cursor.charFormat().fontFamily() != BRAILLE_FONT_NAME:
        #    fmt.setFontFamily(cursor.charFormat().fontFamily())
        # else:
        fmt.setFontFamily(self.current_font)
            
        cursor.mergeCharFormat(fmt)
        # tab.text_input.setFont(QFont(self.current_font, font_size)) # Ne pas appliquer à tout le widget
        # tab.text_output.setFont(QFont(self.current_font, font_size)) # Ne pas appliquer à tout le widget
        self.sync_text_areas(tab)
        self.font_size_spin.setValue(font_size)
        # self.update_line_width() # L'ajustement de la largeur dépend de la police globale, pas de la sélection.
        # self.update_conversion() # La conversion ne dépend pas de la taille de la police, mais du texte.

    def align_text(self, alignment):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.BlockUnderCursor)
        block_format = cursor.blockFormat()
        block_format.setAlignment(alignment)
        cursor.setBlockFormat(block_format)
        self.sync_text_areas(tab)
        self.update_counters()

    def adjust_line_width(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        current_width = self.line_width
        width, ok = QInputDialog.getInt(
            self,
            "Largeur des lignes",
            "Entrez la largeur des lignes (en caractères) :",
            current_width,
            self.min_line_width,
            200,  # Maximum raisonnable
            1
        )
        
        if ok and width != current_width:
            try:
                # Afficher un message de progression
                self.status_bar.showMessage("Ajustement de la largeur en cours...")
                QApplication.processEvents()  # Permettre la mise à jour de l'interface

                # Sauvegarder l'état actuel (pour l'historique des modifications si nécessaire, ou juste pour la robustesse)
                # Cette partie peut être simplifiée car nous ne reformatons pas immédiatement ici.
                # cursor = tab.text_input.textCursor()
                # has_selection = cursor.hasSelection()
                # selection_start = cursor.selectionStart()
                # selection_end = cursor.selectionEnd()

                # Mettre à jour la largeur
                self.line_width = width
                self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")

                # Configurer le retour à la ligne pour qu'il s'adapte à la largeur du widget
                # La logique de formatage pour l'export utilisera la self.line_width mise à jour.
                self.apply_line_width_to_tab(tab) # Cette méthode devrait configurer WidgetWidth

                # Déclencher la mise à jour de la conversion (qui est debounced et threaded)
                self.update_conversion()

                self.status_bar.showMessage(f"Largeur des lignes ajustée à {self.line_width} caractères", 3000)

            except Exception as e:
                logging.error(f"Erreur lors de l'ajustement de la largeur : {str(e)}")
                self.status_bar.showMessage("Erreur lors de l'ajustement de la largeur", 3000)
            finally:
                # Les signaux sont gérés par update_conversion maintenant si nécessaire
                pass # Aucun besoin de blockSignals/unblockSignals ici directement

    def adjust_lines_per_page(self):
        lines_per_page, ok = QInputDialog.getInt(
            self,
            "Nombre de lignes par page",
            "Entrez le nombre maximum de lignes par page :",
            self.lines_per_page,
            10,
            100,
            1,
        )
        if ok:
            self.lines_per_page = lines_per_page
            self.update_counters()
            tab = self.tab_widget.currentWidget()
            if tab:
                current_text = tab.text_input.toPlainText()
                lines = current_text.split('\n')
                formatted_lines = [self.braille_engine.wrap_text_by_sentence(line, self.line_width) for line in lines]
                formatted_text = '\n'.join(formatted_lines)
                tab.text_input.setPlainText(formatted_text)
                self._convert_to_braille(tab, formatted_text)
            self.status_bar.showMessage(
                f"Nombre de lignes par page ajusté à {lines_per_page}", 3000
            )
        else:
            self.status_bar.showMessage("Ajustement des lignes par page annulé", 3000)

    def adjust_line_spacing(self):
        spacing, ok = QInputDialog.getDouble(
            self,
            "Interligne",
            "Entrez l'espacement pour la zone de texte (1.0 par défaut) :",
            self.line_spacing,
            0.5,
            3.0,
            1,
        )
        if ok:
            self.line_spacing = spacing
            tab = self.tab_widget.currentWidget()
            if tab:
                cursor = tab.text_input.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setLineHeight(spacing * 100, QTextBlockFormat.ProportionalHeight)
                cursor.setBlockFormat(block_format)
                tab.text_input.setTextCursor(cursor)
                cursor = tab.text_output.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setLineHeight(spacing * 100, QTextBlockFormat.ProportionalHeight)
                cursor.setBlockFormat(block_format)
                tab.text_output.setTextCursor(cursor)
                self.status_bar.showMessage(
                    f"Interligne ajusté à {spacing}x dans la zone de texte", 3000
                )
            self.update_conversion()
        else:
            self.status_bar.showMessage("Ajustement de l'interligne annulé", 3000)

    def adjust_indent(self):
        indent, ok = QInputDialog.getInt(
            self,
            "Retrait",
            "Entrez le retrait pour la zone de texte (mm) :",
            self.indent,
            0,
            50,
            1,
        )
        if ok:
            self.indent = indent
            tab = self.tab_widget.currentWidget()
            if tab:
                cursor = tab.text_input.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setTextIndent(indent)
                cursor.setBlockFormat(block_format)
                tab.text_input.setTextCursor(cursor)
                cursor = tab.text_output.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setTextIndent(indent)
                cursor.setBlockFormat(block_format)
                tab.text_output.setTextCursor(cursor)
                self.status_bar.showMessage(
                    f"Retrait ajusté à {indent} mm dans la zone de texte", 3000
                )
            self.update_conversion()
        else:
            self.status_bar.showMessage("Ajustement du retrait annulé", 3000)

    def reset_zoom(self):
        """Réinitialise le niveau de zoom à 100%."""
        self.zoom_slider.setValue(100)
        # Appeler apply_zoom avec la valeur actuelle du slider après réinitialisation
        self.apply_zoom(self.zoom_slider.value())

    def toggle_window_size(self):
        if self.isMaximized():
            self.showNormal()
            self.toggle_size_button.setIcon(self.safe_icon("icons/maximize.png"))
        else:
            self.showMaximized()
            self.toggle_size_button.setIcon(self.safe_icon("icons/restore.png"))
        self.update_conversion()

    def sync_text_areas(self, tab):
        if not tab or getattr(tab, 'is_updating', False):
            logging.debug("sync_text_areas skipped: tab is None or is_updating")
            return

        tab.is_updating = True
        logging.debug("Starting sync_text_areas")
        try:
            self._set_text_direction(tab)
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)

            input_cursor = tab.text_input.textCursor()
            input_pos = input_cursor.position()
            output_cursor = tab.text_output.textCursor()
            output_pos = output_cursor.position()
            logging.debug(f"sync_text_areas - Input cursor: {input_pos}, Output cursor: {output_pos}")

            current_input_text = tab.text_input.toPlainText()
            current_output_braille = tab.text_output.toPlainText()
            selected_table = self.table_combo.currentText()

            text_changed = current_input_text != tab.original_text
            braille_changed = current_output_braille != tab.original_braille

            if text_changed:
                logging.debug("Text changed, updating Braille")
                if current_input_text and selected_table:
                    self._convert_to_braille(tab, current_input_text)
                    tab.original_text = current_input_text
                else:
                    tab.text_output.clear()
                    tab.original_braille = ""
            elif braille_changed:
                logging.debug("Braille changed, updating Text")
                if current_output_braille and selected_table:
                    self._convert_to_text(tab, current_output_braille)
                    tab.original_braille = current_output_braille
                else:
                    tab.text_input.clear()
                    tab.original_text = ""

            self._restore_cursor_position(tab.text_input, input_pos)
            self._restore_cursor_position(tab.text_output, output_pos)

            if self.logged_in_user and (text_changed or braille_changed):
                try:
                    tab_title = self.tab_widget.tabText(self.tab_widget.indexOf(tab))
                    texte = Texte(current_input_text[:255], tab_title)
                    self.db.ajouter_texte(self.logged_in_user.id, texte)
                    logging.debug(f"Saved text to database: {tab_title}")
                except Exception as e:
                    logging.error(f"Erreur lors de l'ajout du texte dans la base de données : {str(e)}")
                    self.status_bar.showMessage("Erreur lors de la sauvegarde du texte dans la base de données")
        except Exception as e:
            logging.error(f"Erreur dans sync_text_areas : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la synchronisation du texte.")
        finally:
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            tab.is_updating = False
            logging.debug("Finished sync_text_areas")

    def _set_text_direction(self, tab):
        direction = Qt.RightToLeft if "Arabe" in self.table_combo.currentText() else Qt.LeftToRight
        tab.text_input.setLayoutDirection(direction)
        tab.text_output.setLayoutDirection(direction)

    def _convert_to_braille(self, tab, current_input):
        selected_table = self.available_tables[self.table_combo.currentText()]
        if len(current_input) <= 500:
            lines = current_input.split('\n')
            braille_lines = []
            for line in lines:
                if line.strip():
                    formatted_line = self.braille_engine.wrap_text_by_sentence(line, self.line_width)
                    braille_line = self.braille_engine.to_braille(formatted_line, selected_table, self.line_width)
                    braille_lines.append(braille_line)
                else:
                    braille_lines.append("")
            formatted_braille = '\n'.join(braille_lines)
            tab.text_output.setPlainText(formatted_braille)
            tab.original_braille = formatted_braille
        else:
            progress_dialog = QProgressDialog("Conversion en Braille...", "Annuler", 0, 100, self)
            progress_dialog.setWindowModality(Qt.WindowModal)
            progress_dialog.show()

            thread = BrailleConversionThread(self.braille_engine, current_input, selected_table, self.line_width)
            thread.conversion_done.connect(lambda t, ft, fb: self.on_conversion_done(tab, ft, fb))
            thread.progress_updated.connect(progress_dialog.setValue)
            thread.finished.connect(progress_dialog.close)
            thread.start()
            tab._conversion_thread = thread

    def _convert_to_text(self, tab, current_braille):
        selected_table = self.available_tables[self.table_combo.currentText()]
        braille_lines = current_braille.split('\n')
        text_lines = []
        for line in braille_lines:
            if line.strip():
                formatted_braille_line = self.braille_engine.wrap_text_by_sentence(line, self.line_width)
                text_line = self.braille_engine.from_braille(formatted_braille_line, selected_table, self.line_width)
                text_lines.append(text_line)
            else:
                text_lines.append("")
        formatted_text = '\n'.join(text_lines)
        tab.text_input.setPlainText(formatted_text)
        tab.original_text = formatted_text

    def on_conversion_done(self, tab, formatted_text, formatted_braille):
        if self.tab_widget.currentWidget() != tab:
            return

        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)

        input_cursor = tab.text_input.textCursor()
        output_cursor = tab.text_output.textCursor()
        input_pos = input_cursor.position()
        output_pos = output_cursor.position()

        tab.text_input.setPlainText(formatted_text)
        tab.text_output.setPlainText(formatted_braille)
        tab.original_text = formatted_text
        tab.original_braille = formatted_braille

        self._restore_cursor_position(tab.text_input, input_pos)
        self._restore_cursor_position(tab.text_output, output_pos)

        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)
        tab._conversion_thread = None
        tab.connect_text_changed()
        self.update_counters()

    def test_conversion(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        
        tests = {
            "Français (grade 1)": "Bonjour le monde.",
            "Arabe (grade 1)": "مرحبا بالعالم. هذا اختبار.",
            "Anglais (grade 1)": "Hello World. This is a test.",
            "Anglais (grade 2)": "Hello World. This is a test.",
            "Français (grade 2)": "Bonjour le monde. Ceci est un test."
        }
        
        selected_table = self.table_combo.currentText()
        test_text = tests.get(selected_table, "Test text.")
        
        tab.text_input.setPlainText(test_text)
        self.update_conversion()

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            set_dark_mode(self.app)
            self.dark_mode_action.setIcon(self.safe_icon("icons/moon.png"))
        else:
            set_light_mode(self.app)
            self.dark_mode_action.setIcon(self.safe_icon("icons/sun.png"))
        self.status_bar.showMessage("Mode sombre activé" if self.dark_mode else "Mode clair activé")

    def new_document(self):
        tab = BrailleTab(self, save_type="Texte + Braille")
        tab_title = "Nouveau document"
        self.tab_widget.addTab(tab, tab_title)
        self.tab_widget.setCurrentWidget(tab)
        scale = self.zoom_slider.value() / 100.0
        font_size = int(self.base_font_size * scale)
        tab.text_input.setFont(QFont(self.current_font, font_size))
        tab.text_output.setFont(QFont(self.current_font, font_size))
        welcome_texts = {
            "Français (grade 1)": "Bienvenue dans le convertisseur Texte ↔ Braille !",
            "Arabe (grade 1)": "مرحبا بكم في محول النصوص إلى البرايل!",
            "Anglais (grade 1)": "Welcome to the Text to Braille Converter!"
        }
        selected_table = self.table_combo.currentText()
        welcome_text = welcome_texts.get(selected_table, "Welcome!")
        tab.text_input.setPlainText(welcome_text)
        
        # Installer le filtre d'événements sur la zone de texte d'entrée pour la saisie Braille directe
        tab.text_input.installEventFilter(self)

        
        # Appliquer la largeur de ligne par défaut (33) au nouvel onglet
        self.apply_line_width_to_tab(tab)
        
        tab.connect_text_changed()
        self.sync_text_areas(tab)
        self.update_conversion()

    def close_tab(self, index):
        tab = self.tab_widget.widget(index)
        if tab and (tab.text_input.toPlainText().strip() or tab.text_output.toPlainText().strip()):
            tab_title = self.tab_widget.tabText(index)
            reply = QMessageBox.question(
                self, "Confirmer", f"Voulez-vous fermer l'onglet '{tab_title}' ? Les modifications non sauvegardées seront perdues.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        self.tab_widget.removeTab(index)
        if self.tab_widget.count() == 0:
            self.new_document()

    def clean_text(self, text):
        """Nettoie le texte en supprimant les caractères invisibles ou non pris en charge."""
        cleaned_text = ''.join(char for char in text if char.isprintable() or char == '\n')
        cleaned_text = ''.join(char if ord(char) < 0x1100 else ' ' for char in cleaned_text)
        return cleaned_text

    def import_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Importer des fichiers", "",
            "Tous les fichiers (*.txt *.bfr *.pdf *.docx);;Fichiers texte (*.txt *.bfr);;Fichiers PDF (*.pdf);;Fichiers Word (*.docx)")
        if not file_paths:
            return

        progress = QProgressDialog("Importation des fichiers...", "Annuler", 0, len(file_paths), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()

        for i, file_path in enumerate(file_paths):
            if progress.wasCanceled():
                break

            progress.setValue(i)
            progress.setLabelText(f"Importation de {os.path.basename(file_path)}...")

            start_extract = time.time()
            try:
                text = self.file_handler.extract_text(file_path, max_pages=10)
                text = self.clean_text(text)
            except Exception as e:
                logging.error(f"Erreur lors de l'extraction de {file_path} : {str(e)}")
                text = "Erreur lors de l'extraction du fichier."

            extract_time = time.time() - start_extract
            logging.debug(f"Temps d'extraction pour {file_path}: {extract_time:.2f} secondes")

            if not text:
                text = "Fichier non pris en charge ou corrompu."

            save_type = "Texte uniquement"
            filtered_text = text
            if file_path.endswith(".bfr"):
                save_type = "Braille uniquement"
                filtered_text = ''.join(char for char in text if ('\u2800' <= char <= '\u28FF') or char.isspace())
            else:
                filtered_text = ''.join(char for char in text if not ('\u2800' <= char <= '\u28FF'))

            tab = BrailleTab(self, file_path=file_path, save_type=save_type)
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)

            # Installer le filtre d'événements sur la zone de texte d'entrée pour la saisie Braille directe
            tab.text_input.installEventFilter(self)

            # Configurer la largeur de ligne pour le nouvel onglet
            tab.text_input.setLineWrapMode(QTextEdit.WidgetWidth)
            tab.text_output.setLineWrapMode(QTextEdit.WidgetWidth)

            # Définir la largeur minimale
            min_width = self.line_width * tab.text_input.fontMetrics().averageCharWidth()
            tab.text_input.setMinimumWidth(int(min_width))
            tab.text_output.setMinimumWidth(int(min_width))

            if file_path.endswith(".bfr"):
                tab.text_output.setPlainText(filtered_text)
                tab.original_braille = filtered_text
            else:
                # Formater le texte en préservant les mots
                words = filtered_text.split()
                formatted_lines = []
                current_line = []
                current_length = 0
                
                for word in words:
                    word_length = len(word)
                    if current_length + word_length + len(current_line) <= self.line_width:
                        current_line.append(word)
                        current_length += word_length
                    else:
                        if current_line:
                            formatted_lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = word_length
                
                if current_line:
                    formatted_lines.append(' '.join(current_line))
                
                formatted_text = '\n'.join(formatted_lines)
                tab.text_input.setPlainText(formatted_text)
                tab.original_text = formatted_text

                if formatted_text.strip():
                    selected_table = self.table_combo.currentText()
                    if selected_table:
                        try:
                            start_convert = time.time()
                            thread = BrailleConversionThread(self.braille_engine, formatted_text,
                                                            self.available_tables[selected_table], self.line_width)
                            thread.conversion_done.connect(lambda _, ft, fb: self.on_conversion_done(tab, ft, fb))
                            thread.start()
                            tab._conversion_thread = thread
                            logging.debug(f"Démarrage de la conversion pour {file_path}...")
                        except Exception as e:
                            logging.error(f"Erreur lors de la conversion de {file_path} : {str(e)}")
                            tab.text_output.setPlainText("Erreur lors de la conversion en Braille.")
                    else:
                        tab.text_output.clear()
                else:
                    tab.text_output.clear()

            scale = self.zoom_slider.value() / 100.0
            font_size = int(self.base_font_size * scale)
            tab.text_input.setFont(QFont(self.current_font, font_size))
            tab.text_output.setFont(QFont(self.current_font, font_size))
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            tab.connect_text_changed()

            tab_title = os.path.basename(file_path)
            self.tab_widget.addTab(tab, tab_title)
            if self.logged_in_user:
                try:
                    fichier = Fichier(tab_title, file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier, 'import', tab.save_type)
                except Exception as e:
                    logging.error(f"Erreur lors de l'ajout du fichier dans la base de données : {str(e)}")
                    self.status_bar.showMessage("Erreur lors de la sauvegarde du fichier dans la base de données")

        progress.setValue(len(file_paths))
        progress.close()
        if file_paths:
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            self.update_counters()

    def import_image(self):
        image_formats = (
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff *.ico *.jfif *.heic *.heif "
            "*.avif *.apng *.pnm *.pgm *.ppm *.pbm *.svg *.tga *.exr *.jp2 *.j2k *.jpf *.jpx "
            "*.jpm *.mj2 *.hdr *.pic *.wdp *.hdp *.jng *.mng *.pfm *.sr *.ras *.rgb *.rgba *.rgbz)"
        )
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer une image", "", image_formats)
        if not file_path:
            return

        if not os.path.exists(file_path):
            QMessageBox.critical(self, "Erreur", "Le fichier image n'existe pas.")
            return

        if not os.access(file_path, os.R_OK):
            QMessageBox.critical(self, "Erreur", "Permission refusée pour lire le fichier image.")
            return

        dialog = QInputDialog(self)
        dialog.setWindowTitle("Options de conversion d'image")
        dialog.setLabelText("Choisissez le mode de conversion :")
        dialog.setComboBoxItems(["Texte (OCR)", "Graphique (Courbes/Formes)", "Hybride (Texte + Graphique)"])
        dialog.setOkButtonText("Convertir")
        dialog.setCancelButtonText("Annuler")
        
        if not dialog.exec_():
            return
                
        mode_map = {
            "Texte (OCR)": "text",
            "Graphique (Courbes/Formes)": "graphic",
            "Hybride (Texte + Graphique)": "hybrid"
        }
        mode = mode_map[dialog.textValue()]

        try:
            extracted_text, braille_text = self.file_handler.image_to_braille(file_path, mode=mode)
            if not braille_text.strip():
                QMessageBox.warning(self, "Avertissement", "Aucun contenu Braille généré.")
                return

            tab = BrailleTab(self, file_path=file_path, save_type="Texte + Braille")
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)
            
            cursor = tab.text_input.textCursor()
            image_format = QTextImageFormat()
            image_format.setName(file_path)
            image_format.setWidth(300)
            cursor.insertImage(image_format)
            
            if extracted_text.strip():
                cursor.insertText("\n\nTexte extrait :\n" + extracted_text)
            
            tab.original_text = extracted_text if extracted_text else ""
            tab.text_output.setPlainText(braille_text)
            tab.original_braille = braille_text
            
            scale = self.zoom_slider.value() / 100.0
            font_size = int(self.base_font_size * scale)
            tab.text_input.setFont(QFont(self.current_font, font_size))
            tab.text_output.setFont(QFont(self.current_font, font_size))
            
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            tab.connect_text_changed()

            tab_title = os.path.basename(file_path)
            self.tab_widget.addTab(tab, tab_title)
            self.update_counters()
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            
            if self.logged_in_user:
                try:
                    fichier = Fichier(tab_title, file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier, 'import', mode)
                except Exception as e:
                    logging.error(f"Erreur lors de l'ajout de l'image dans la base de données : {str(e)}")
                    self.status_bar.showMessage("Erreur lors de la sauvegarde de l'image dans la base de données")
                
        except Exception as e:
            logging.error(f"Erreur lors de l'importation de l'image : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'importation : {str(e)}")

    def _save_or_export(self, tab, file_path=None, export_format="txt", prompt_save_type=True):
        if not tab or (not tab.text_input.toPlainText().strip() and not tab.text_output.toPlainText().strip()):
            QMessageBox.warning(self, "Avertissement", "Aucun contenu à sauvegarder.")
            return False

        save_type = tab.save_type
        if prompt_save_type:
            export_choice, ok = QInputDialog.getItem(
                self, "Options", "Choisissez le contenu :",
                ["Texte + Braille", "Braille uniquement", "Texte uniquement"], 0, False
            )
            if not ok:
                return False
            save_type = export_choice

        if not file_path:
            filters = {
                "txt": "Fichiers texte (*.txt);;Fichiers Braille (*.bfr)",
                "pdf": "Fichiers PDF (*.pdf)",
                "docx": "Fichiers Word (*.docx)",
                "gcode": "Fichiers Gcode (*.gcode)"
            }
            file_path, _ = QFileDialog.getSaveFileName(self, f"Enregistrer sous {export_format.upper()}", "", filters[export_format])
            if not file_path:
                return False

        doc_name = os.path.basename(file_path) if file_path else "Nouveau document"

        try:
            if export_format == "pdf":
                self.file_handler.export_pdf(file_path, tab.text_input.document(), tab.text_output.toPlainText(), 
                                            save_type, font_name=self.current_font, doc_name=doc_name)
            elif export_format == "docx":
                self.file_handler.export_docx(file_path, tab.text_input.document(), tab.text_output.toPlainText(), 
                                             save_type, font_name=self.current_font, doc_name=doc_name)
            elif export_format == "gcode":
                gcode_content = self.file_handler.convert_to_gcode(tab.text_output.toPlainText())
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(gcode_content)
            else:
                content = (
                    tab.text_input.toPlainText() + "\n\n" + tab.text_output.toPlainText()
                    if save_type == "Texte + Braille" else
                    tab.text_output.toPlainText() if save_type == "Braille uniquement" else
                    tab.text_input.toPlainText()
                )
                self.file_handler.save_text(file_path, content)

            tab.file_path = file_path
            tab.save_type = save_type
            tab_title = os.path.basename(file_path)
            self.tab_widget.setTabText(self.tab_widget.indexOf(tab), tab_title)
            QMessageBox.information(self, "Succès", f"Fichier sauvegardé : {file_path}")

            if self.logged_in_user:
                try:
                    fichier = Fichier(tab_title, file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier, 'export', tab.save_type)
                except Exception as e:
                    logging.error(f"Erreur lors de l'ajout du fichier sauvegardé dans la base de données : {str(e)}")
                    self.status_bar.showMessage("Erreur lors de la sauvegarde du fichier dans la base de données")
            return True

        except Exception as e:
            logging.error(f"Erreur lors de la sauvegarde : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")
            return False

    def save_document(self):
        tab = self.tab_widget.currentWidget()
        if tab and tab.file_path and os.path.exists(tab.file_path):
            self._save_or_export(tab, tab.file_path, os.path.splitext(tab.file_path)[1][1:], False)
        else:
            self.save_document_as()

    def save_document_as(self):
        tab = self.tab_widget.currentWidget()
        self._save_or_export(tab)

    def save_braille_text(self):
        tab = self.tab_widget.currentWidget()
        if not tab or not tab.text_output.toPlainText().strip():
            QMessageBox.warning(self, "Avertissement", "Aucun texte Braille à sauvegarder.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Sauvegarder le texte en Braille", "",
                                                   "Fichiers texte (*.txt);;Fichiers Braille (*.bfr)")
        if file_path:
            try:
                self.file_handler.save_text(file_path, tab.text_output.toPlainText())
                tab.file_path = file_path
                tab_title = os.path.basename(file_path)
                self.tab_widget.setTabText(self.tab_widget.indexOf(tab), tab_title)
                QMessageBox.information(self, "Succès", f"Texte Braille sauvegardé dans {file_path}")
                if self.logged_in_user:
                    try:
                        fichier = Fichier(tab_title, file_path)
                        self.db.sauvegarder_fichier(self.logged_in_user.id, fichier, 'export', tab.save_type)
                    except Exception as e:
                        logging.error(f"Erreur lors de l'ajout du fichier Braille dans la base de données : {str(e)}")
                        self.status_bar.showMessage("Erreur lors de la sauvegarde du fichier dans la base de données")
            except Exception as e:
                logging.error(f"Erreur lors de la sauvegarde du texte Braille : {str(e)}")
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")

    def export_to_pdf(self):
        self._save_or_export(self.tab_widget.currentWidget(), export_format="pdf")

    def export_to_word(self):
        self._save_or_export(self.tab_widget.currentWidget(), export_format="docx")

    def export_to_gcode(self):
        self._save_or_export(self.tab_widget.currentWidget(), export_format="gcode")

    def print_braille(self):
        tab = self.tab_widget.currentWidget()
        if not tab or not tab.text_output.toPlainText().strip():
            QMessageBox.warning(self, "Avertissement", "Aucun texte Braille à imprimer.")
            return

        printer = QPrinter(QPrinter.HighResolution)
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() != QPrintDialog.Accepted:
            return

        try:
            braille_text = tab.text_output.toPlainText()
            formatted_braille = self.braille_engine.wrap_text_by_sentence(braille_text, self.line_width)
            doc = tab.text_output.document().clone()
            doc.setPlainText(formatted_braille)
            
            font = QFont(self.current_font, self.base_font_size)
            doc.setDefaultFont(font)
            
            cursor = QTextCursor(doc)
            block_format = QTextBlockFormat()
            block_format.setLineHeight(self.line_spacing * 100, QTextBlockFormat.ProportionalHeight)
            block_format.setTextIndent(self.indent)
            cursor.select(QTextCursor.Document)
            cursor.setBlockFormat(block_format)
            
            lines = formatted_braille.split("\n")
            pages = []
            current_page = []
            
            for line in lines:
                current_page.append(line)
                if len(current_page) >= self.lines_per_page:
                    pages.append("\n".join(current_page))
                    current_page = []
            if current_page:
                pages.append("\n".join(current_page))
            
            tab_title = self.tab_widget.tabText(self.tab_widget.indexOf(tab))
            doc_name = os.path.basename(tab.file_path) if tab.file_path else tab_title
            printer.setDocName(doc_name)
            doc.print_(printer)
            
            QMessageBox.information(self, "Succès", f"Impression Braille de '{doc_name}' terminée.")
            
            if self.logged_in_user:
                try:
                    impression = Impression(doc_name)
                    self.db.ajouter_impression(self.logged_in_user.id, impression)
                except Exception as e:
                    logging.error(f"Erreur lors de l'ajout de l'impression dans la base de données : {str(e)}")
                    self.status_bar.showMessage("Erreur lors de la sauvegarde de l'impression dans la base de données")
        except Exception as e:
            logging.error(f"Erreur lors de l'impression : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'impression : {str(e)}")

    def show_custom_table(self):
        try:
            dialog = CustomBrailleTableWidget(self.braille_engine, self)
            if dialog.exec_():
                self.braille_engine.update_custom_table()
                self.table_combo.clear()
                self.table_combo.addItems(self.braille_engine.get_available_tables().keys())
                self.table_combo.setCurrentText("Personnalisée" if "Personnalisée" in self.braille_engine.get_available_tables() else "Français (grade 1)")
                self.update_conversion()
                self.status_bar.showMessage("Tableau Braille personnalisé mis à jour", 3000)
        except Exception as e:
            logging.error(f"Erreur dans show_custom_table : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la personnalisation : {str(e)}")

    def show_usage_stats(self):
        if not self.logged_in_user:
            QMessageBox.warning(self, "Avertissement", "Vous devez être connecté pour voir les statistiques.")
            return
        try:
            stats = self.db.get_usage_stats(self.logged_in_user.id)
            total_time = stats.get('total_usage_time', 0)
            # Calculer le nombre total de fichiers traités (somme des importations et exportations)
            files_imported = sum(sum(formats.values()) for formats in stats.get('file_stats', {}).get('import', {}).values())
            files_exported = sum(sum(formats.values()) for formats in stats.get('file_stats', {}).get('export', {}).values())
            total_files_processed = files_imported + files_exported


            prints = stats.get('print_count', 0)
            hours, remainder = divmod(total_time, 3600)
            minutes, seconds = divmod(remainder, 60)

            message = (
                f"Statistiques d'utilisation pour {self.current_email}:\n\n"
                f"Temps total d'utilisation: {hours}h {minutes}m {seconds}s\n"
                f"Total des fichiers traités: {total_files_processed}\n"
            )

            # Mapping pour afficher les noms complets des save_types
            save_type_display_map = {
                "Texte + Braille": "Texte + Braille",
                "Braille uniquement": "Braille uniquement",
                "Texte uniquement": "Texte uniquement",
                "text": "Image (Texte OCR)",
                "graphic": "Image (Graphique)",
                "hybrid": "Image (Hybride)"
            }


            # Ajouter les détails des fichiers importés avec save_type
            import_stats = stats.get('file_stats', {}).get('import', {})
            if import_stats:
                message += "\nFichiers importés :\n"
                for file_type, save_types in import_stats.items():
                    for save_type, count in save_types.items():
                         display_save_type = save_type_display_map.get(save_type, save_type) # Utiliser le mapping
                         message += f"- {file_type.upper()} ({display_save_type}): {count}\n"


            # Ajouter les détails des fichiers exportés avec save_type
            export_stats = stats.get('file_stats', {}).get('export', {})
            if export_stats:
                message += "\nFichiers exportés :\n"
                for file_type, save_types in export_stats.items():
                     for save_type, count in save_types.items():
                        display_save_type = save_type_display_map.get(save_type, save_type) # Utiliser le mapping
                        message += f"- {file_type.upper()} ({display_save_type}): {count}\n"

            message += f"\nImpressions Braille: {prints}"

            QMessageBox.information(self, "Statistiques", message)
        except Exception as e:
            logging.error(f"Erreur dans show_usage_stats : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la récupération des statistiques : {str(e)}")

    def clear_text(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        if tab.text_input.toPlainText().strip() or tab.text_output.toPlainText().strip():
            reply = QMessageBox.question(
                self, "Confirmer", "Voulez-vous effacer tout le contenu ?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        tab.text_input.clear()
        tab.text_output.clear()
        tab.original_text = ""
        tab.original_braille = ""
        self.update_counters()
        self.status_bar.showMessage("Contenu effacé", 3000)

    def update_counters(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            self.page_count.setText("0")
            self.line_count.setText("0")
            self.word_count.setText("0")
            return

        try:
            text = tab.text_input.toPlainText()
            # Calculer le nombre de lignes visuelles en tenant compte du wrapping
            visual_line_count = 0
            document = tab.text_input.document()
            block = document.begin()
            while block.isValid():
                layout = block.layout()
                if layout:
                    visual_line_count += layout.lineCount()
                block = block.next()

            line_count = visual_line_count # Utiliser le nombre de lignes visuelles
            word_count = sum(len(re.findall(r'\b\w+\b', line)) for line in text.split('\n'))
            page_count = (line_count + self.lines_per_page - 1) // self.lines_per_page if self.lines_per_page > 0 else 1

            self.page_count.setText(str(page_count))
            self.line_count.setText(str(line_count))
            self.word_count.setText(str(word_count))

            self.status_bar.showMessage(
                f"{getattr(self, 'current_usage_time_str', 'Temps d\'utilisation : --:--:--')} | Pages: {page_count} | Lignes: {line_count} | Mots: {word_count}", 3000
            )
        except Exception as e:
            logging.error(f"Erreur dans update_counters : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la mise à jour des compteurs.")

    def on_text_changed(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        if not tab.is_updating:
            logging.debug("on_text_changed: conversion en temps réel")
            self.update_conversion()

    def process_debounced_conversion(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        tab.process_pending_changes()
        self.update_conversion()

    def update_conversion(self):
        tab = self.tab_widget.currentWidget()
        if not tab or getattr(tab, 'is_updating', False):
            logging.debug("update_conversion skipped: no tab or updating")
            return

        if tab._conversion_thread and tab._conversion_thread.isRunning():
            logging.debug("update_conversion skipped: conversion thread is running")
            return

        tab.is_updating = True
        logging.debug("Déclenchement de la conversion en temps réel")
        try:
            # Désactiver temporairement les signaux pour éviter les boucles de conversion
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)

            current_input_text = tab.text_input.toPlainText()
            current_output_braille = tab.text_output.toPlainText()
            selected_table = self.table_combo.currentText()

            # Déterminer quelle zone de texte a probablement déclenché le changement (pas parfait, mais aide)
            # Une approche plus robuste nécessiterait de suivre le focus ou d'utiliser des signaux personnalisés.
            # Ici, nous nous basons sur le mode de conversion pour déterminer quelle zone est l'entrée principale.

            if self.conversion_mode == "text_to_braille":
                # En mode Texte -> Braille, la zone d'entrée principale est text_input
                if current_input_text != tab.original_text:
                    logging.debug("Mode Texte->Braille: text_input changed, converting to Braille")
                    if current_input_text.strip():
                        # Effectuer une reconversion complète lorsque le texte d'entrée change
                        formatted_text = self.braille_engine.wrap_text_by_sentence(current_input_text, self.line_width)
                        formatted_braille = self.braille_engine.to_braille(formatted_text, self.available_tables[selected_table], self.line_width)
                        tab.text_output.setPlainText(formatted_braille)
                        tab.original_braille = formatted_braille
                        tab.original_text = current_input_text
                    else:
                        tab.text_output.clear()
                        tab.original_braille = ""

            elif self.conversion_mode == "braille_to_text":
                # En mode Braille -> Texte, la zone d'entrée principale est text_input (où on tape le Braille)
                # et la zone de sortie est text_output (où le texte clair apparaît)
                if current_input_text != tab.original_braille: # En mode Braille, original_braille stocke le *braille* tapé dans text_input
                    logging.debug("Mode Braille->Texte: text_input (Braille) changed, converting to Text")
                    if current_input_text.strip():
                        # Effectuer une conversion Braille -> Texte
                        # La fonction from_braille gère déjà le wrapping si nécessaire.
                        text = self.braille_engine.from_braille(current_input_text, self.available_tables[selected_table], self.line_width)
                        tab.text_output.setPlainText(text)
                        tab.original_text = text # original_text stocke maintenant le texte clair généré
                        tab.original_braille = current_input_text # original_braille stocke le Braille tapé
                    else:
                        tab.text_output.clear()
                        tab.original_text = ""

            # Note: Les changements dans text_output (zone de droite) ne déclenchent pas de conversion automatique
            # dans aucun mode pour éviter les boucles ou comportements imprévus lorsque l'utilisateur modifie la sortie.
            # L'utilisateur est censé modifier la zone d'entrée principale (text_input).

            # Restaurer la position du curseur (peut nécessiter un ajustement pour les modes bidirectionnels plus complexes)
            # Pour l'instant, nous restaurons juste la position dans les deux zones, ce qui est acceptable pour l'entrée simple.
            self._restore_cursor_position(tab.text_input, tab.text_input.textCursor().position())
            self._restore_cursor_position(tab.text_output, tab.text_output.textCursor().position())

        except Exception as e:
            logging.error(f"Erreur dans update_conversion : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la conversion.")
        finally:
            # Réactiver les signaux
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            tab.is_updating = False
            self.update_counters()

    def _restore_cursor_position(self, text_edit, position):
        cursor = text_edit.textCursor()
        if cursor.hasSelection():
            # Préserver la sélection
            start = cursor.selectionStart()
            end = cursor.selectionEnd()
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.KeepAnchor)
        else:
            # Restaurer uniquement la position du curseur
            cursor.setPosition(min(position, len(text_edit.toPlainText())))
        text_edit.setTextCursor(cursor)

    def closeEvent(self, event):
        if self.logged_in_user:
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        self.braille_engine.shutdown()
        event.accept()

    def handle_resize(self):
        if not self.resize_timer.isActive():
            tab = self.tab_widget.currentWidget()
            if tab:
                # Supprimer l'appel à update_line_width() ici
                # self.update_line_width()
                self.update_conversion()

    def update_line_width(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        try:
            # Calculer la nouvelle largeur
            font_metrics_input = QFontMetrics(tab.text_input.font())
            font_metrics_output = QFontMetrics(tab.text_output.font())
            char_width_input = font_metrics_input.averageCharWidth()
            char_width_output = font_metrics_output.averageCharWidth()
            scale = self.zoom_slider.value() / 100.0
            
            # Utiliser la plus petite largeur disponible pour les deux zones
            available_width_input = tab.text_input.viewport().width()
            available_width_output = tab.text_output.viewport().width()
            available_width = min(available_width_input, available_width_output)
            
            # Calculer la largeur en utilisant la plus grande largeur de caractère
            char_width = max(char_width_input, char_width_output)
            new_width = max(self.min_line_width, int(available_width / (char_width * scale)))
            
            if new_width != self.line_width:
                self.line_width = new_width
                self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")
                
                # Appliquer la nouvelle largeur aux deux zones
                self.apply_line_width_to_tab(tab)
                
                self.status_bar.showMessage(f"Largeur des lignes ajustée à {self.line_width} caractères", 3000)

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de la largeur : {str(e)}")
            self.status_bar.showMessage("Erreur lors de l'ajustement de la largeur", 3000)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Augmenter le délai pour éviter les mises à jour trop fréquentes
        self.resize_timer.start(500)

    def update_usage_time(self):
        if self.logged_in_user:
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            # Calculer le temps écoulé et formater la chaîne
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.current_usage_time_str = f"Temps d'utilisation : {hours:02d}:{minutes:02d}:{seconds:02d}"
            
            # Mettre à jour l'affichage dans la barre de statut via update_counters
            self.update_counters() # Appeler pour rafraîchir le message de la barre de statut
        else:
            # Si l'utilisateur n'est pas connecté, le timer continue de tourner, mais on n'enregistre pas.
            # On peut afficher le temps depuis le démarrage de l'app.
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            hours, remainder = divmod(elapsed, 3600)
            minutes, seconds = divmod(remainder, 60)
            self.current_usage_time_str = f"Temps d'utilisation : {hours:02d}:{minutes:02d}:{seconds:02d}"

    def mousePressEvent(self, event):
        # Empêcher la propagation de l'événement si nécessaire
        if event.button() == Qt.LeftButton:
            super().mousePressEvent(event)
        else:
            event.ignore()

    def mouseReleaseEvent(self, event):
        # Empêcher la propagation de l'événement si nécessaire
        if event.button() == Qt.LeftButton:
            super().mouseReleaseEvent(event)
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        # Empêcher la propagation de l'événement si nécessaire
        super().mouseMoveEvent(event)

    def test_pdf_styles(self):
        """Teste l'exportation PDF avec différents styles de texte."""
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        # Créer un texte de test avec différents styles
        test_text = """Test des styles dans l'exportation PDF

Texte normal
Texte en gras
Texte en italique
Texte souligné
Texte en gras et italique
Texte en gras et souligné
Texte en italique et souligné
Texte en gras, italique et souligné

Paragraphe avec alignement à gauche
Paragraphe avec alignement au centre
Paragraphe avec alignement à droite
Paragraphe avec alignement justifié

Texte avec retrait
Texte avec espacement des lignes modifié
Texte avec différentes tailles de police"""

        # Appliquer les styles
        cursor = tab.text_input.textCursor()
        cursor.select(QTextCursor.Document)
        cursor.removeSelectedText()
        cursor.insertText(test_text)

        # Réinitialiser le curseur
        cursor.setPosition(0)
        cursor.movePosition(QTextCursor.Start)

        # Appliquer les styles ligne par ligne
        lines = test_text.split('\n')
        for i, line in enumerate(lines):
            if line.strip():
                cursor.movePosition(QTextCursor.StartOfLine)
                cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                
                # Appliquer les styles selon la ligne
                if "gras" in line.lower():
                    fmt = QTextCharFormat()
                    fmt.setFontWeight(QFont.Bold)
                    cursor.mergeCharFormat(fmt)
                if "italique" in line.lower():
                    fmt = QTextCharFormat()
                    fmt.setFontItalic(True)
                    cursor.mergeCharFormat(fmt)
                if "souligné" in line.lower():
                    fmt = QTextCharFormat()
                    fmt.setFontUnderline(True)
                    cursor.mergeCharFormat(fmt)
                
                # Appliquer les alignements
                if "gauche" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setAlignment(Qt.AlignLeft)
                    cursor.setBlockFormat(block_format)
                elif "centre" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setAlignment(Qt.AlignCenter)
                    cursor.setBlockFormat(block_format)
                elif "droite" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setAlignment(Qt.AlignRight)
                    cursor.setBlockFormat(block_format)
                elif "justifié" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setAlignment(Qt.AlignJustify)
                    cursor.setBlockFormat(block_format)
                
                # Appliquer le retrait
                if "retrait" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setTextIndent(20)
                    cursor.setBlockFormat(block_format)
                
                # Appliquer l'espacement des lignes
                if "espacement" in line.lower():
                    block_format = QTextBlockFormat()
                    block_format.setLineHeight(150, QTextBlockFormat.ProportionalHeight)
                    cursor.setBlockFormat(block_format)
                
                # Appliquer différentes tailles de police
                if "tailles" in line.lower():
                    fmt = QTextCharFormat()
                    fmt.setFontPointSize(16)
                    cursor.mergeCharFormat(fmt)
            
            cursor.movePosition(QTextCursor.NextBlock)

        # Mettre à jour la conversion
        self.update_conversion()

        # Exporter en PDF
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Sauvegarder le test des styles",
            "",
            "Fichiers PDF (*.pdf)"
        )
        
        if file_path:
            try:
                self.file_handler.export_pdf(
                    file_path,
                    tab.text_input.document(),
                    tab.text_output.toPlainText(),
                    "Texte + Braille",
                    font_name=self.current_font,
                    doc_name="Test des styles PDF"
                )
                QMessageBox.information(
                    self,
                    "Test des styles",
                    "Le fichier PDF de test a été généré avec succès.\nVeuillez vérifier que tous les styles sont correctement appliqués."
                )
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Erreur",
                    f"Erreur lors de la génération du PDF de test : {str(e)}"
                )

    def translate_text(self):
        """Traduit le texte sélectionné ou tout le texte."""
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        # Ouvrir la boîte de dialogue de traduction
        dialog = TranslationDialog(self)
        if dialog.exec_() != QDialog.Accepted:
            return

        try:
            # Obtenir le texte à traduire
            cursor = tab.text_input.textCursor()
            if cursor.hasSelection():
                text_to_translate = cursor.selectedText()
            else:
                text_to_translate = tab.text_input.toPlainText()

            if not text_to_translate.strip():
                QMessageBox.warning(self, "Avertissement", "Aucun texte à traduire.")
                return

            # Effectuer la traduction
            translated_text = self.translator.translate_text(
                text_to_translate,
                dialog.source_lang.currentText(),
                dialog.target_lang.currentText()
            )

            # Remplacer le texte
            if cursor.hasSelection():
                cursor.insertText(translated_text)
            else:
                tab.text_input.setPlainText(translated_text)

            self.status_bar.showMessage("Traduction terminée", 3000)
            self.update_conversion()

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la traduction : {str(e)}")

    def detect_language(self):
        """Détecte la langue du texte sélectionné ou tout le texte."""
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        try:
            # Obtenir le texte à analyser
            cursor = tab.text_input.textCursor()
            if cursor.hasSelection():
                text_to_analyze = cursor.selectedText()
            else:
                text_to_analyze = tab.text_input.toPlainText()

            if not text_to_analyze.strip():
                QMessageBox.warning(self, "Avertissement", "Aucun texte à analyser.")
                return

            # Détecter la langue
            detected_lang = self.translator.detect_language(text_to_analyze)
            if detected_lang:
                QMessageBox.information(self, "Langue détectée", f"La langue détectée est : {detected_lang}")
            else:
                QMessageBox.warning(self, "Langue non détectée", "Impossible de détecter la langue du texte.")

        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la détection de la langue : {str(e)}")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    stderr_handler = StderrToLog()
    sys.stderr = stderr_handler
    window = BrailleUI(app)
    window.show()
    sys.exit(app.exec_())