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
    QApplication, QSpacerItem, QSizePolicy, QProgressDialog, QFontComboBox
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QTime, QSize, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QFont, QTextCharFormat, QTextCursor, QTextBlockFormat, QTextImageFormat
from PyQt5.QtPrintSupport import QPrintDialog, QPrinter
from backend.braille_engine import BrailleEngine
from backend.file_handler import FileHandler
from backend.database import Database
from backend.models import Texte, Fichier, Impression
from backend.config import BRAILLE_FONT_NAME
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

    def __init__(self, braille_engine, text, table, line_width):
        super().__init__()
        self.braille_engine = braille_engine
        self.text = text
        self.table = table
        self.line_width = line_width
        self.full_text = text
        self.limit = 1000

    def run(self):
        start_convert = time.time()
        text_to_convert = self.text[:self.limit] if len(self.text) > self.limit else self.text
        formatted_text = self.braille_engine.wrap_text_by_sentence(text_to_convert, self.line_width)
        braille_text = self.braille_engine.to_braille(formatted_text, self.table, self.line_width)
        formatted_braille = self.braille_engine.wrap_text_by_sentence(braille_text, self.line_width)
        
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
        self.init_ui()

    def init_ui(self):
        layout = QHBoxLayout(self)
        self.text_input = QTextEdit()
        self.text_output = QTextEdit()
        self.text_input.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        self.text_output.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        layout.addWidget(self.text_input)
        layout.addWidget(self.text_output)
        self.text_input.textChanged.connect(self.on_text_changed)
        self.text_output.textChanged.connect(self.on_text_changed)

    def on_text_changed(self):
        if not self.is_updating:
            self.text_input.setStyleSheet("QTextEdit { border: 2px solid blue; }")
            self.text_output.setStyleSheet("QTextEdit { border: 2px solid orange; }")
            QTimer.singleShot(1000, self.reset_borders)
            self.parent.update_conversion()

    def reset_borders(self):
        self.text_input.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        self.text_output.setStyleSheet("QTextEdit { border: 1px solid gray; }")

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
        self.available_tables = self.braille_engine.get_available_tables()

        self.dark_mode = False
        self.line_width = 33
        self.min_line_width = 5
        self.lines_per_page = 29
        self.line_spacing = 1.0
        self.indent = 0
        self.current_font = BRAILLE_FONT_NAME
        self.base_font_size = 18
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize)
        self.conversion_timer = QTimer()
        self.conversion_timer.setSingleShot(True)
        self.conversion_timer.timeout.connect(self._trigger_conversion)
        self.is_typing = False
        self.typing_timer = QTimer()
        self.typing_timer.setSingleShot(True)
        self.typing_timer.timeout.connect(self._end_typing)
        self.logged_in_user = None
        self.current_email = None
        self.usage_timer = QTimer()
        self.usage_timer.timeout.connect(self.update_usage_time)
        self.usage_timer.start(1000)

        self.init_ui()

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
        settings_menu.addAction("Ajuster la largeur des lignes", self.adjust_line_width)
        settings_menu.addAction("Ajuster le nombre de lignes par page", self.adjust_lines_per_page)
        settings_menu.addAction("Ajuster l'interligne", self.adjust_line_spacing)
        settings_menu.addAction("Ajuster le retrait", self.adjust_indent)
        settings_menu.addAction("Personnaliser table Braille", self.show_custom_table)
        settings_menu.addAction("Voir les statistiques d'utilisation", self.show_usage_stats)
        settings_menu.addAction("Tester la conversion", self.test_conversion)

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
            ("icons/invert.png", "Inverser Texte/Braille", self.invert_text, "invert_action"),
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
        if not tab:
            return

        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)

        input_text = tab.text_input.toPlainText()
        output_text = tab.text_output.toPlainText()

        input_cursor = tab.text_input.textCursor()
        output_cursor = tab.text_output.textCursor()
        input_cursor_pos = input_cursor.position()
        output_cursor_pos = output_cursor.position()

        tab.text_input.setPlainText(output_text)
        tab.text_output.setPlainText(input_text)
        tab.original_text = output_text
        tab.original_braille = input_text

        new_input_cursor = tab.text_input.textCursor()
        new_output_cursor = tab.text_output.textCursor()
        new_input_cursor.setPosition(min(output_cursor_pos, len(output_text)))
        new_output_cursor.setPosition(min(input_cursor_pos, len(input_text)))
        tab.text_input.setTextCursor(new_input_cursor)
        tab.text_output.setTextCursor(new_output_cursor)

        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)

        self.update_conversion()
        self.status_bar.showMessage("Texte et Braille inversés")

    def keyPressEvent(self, event):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        key = event.key()
        logging.debug(f"Key pressed: {key}")

        if not (event.modifiers() & Qt.ControlModifier) and (
            (Qt.Key_A <= key <= Qt.Key_Z) or
            (Qt.Key_0 <= key <= Qt.Key_9) or
            key in (Qt.Key_Space, Qt.Key_Period, Qt.Key_Comma, Qt.Key_Apostrophe, Qt.Key_QuoteDbl)
        ):
            self.is_typing = True
            self.typing_timer.start(500)
            tab.text_input.setStyleSheet("QTextEdit { border: 2px solid blue; }")
            tab.text_output.setStyleSheet("QTextEdit { border: 2px solid orange; }")
            QTimer.singleShot(1000, tab.reset_borders)
            super().keyPressEvent(event)
            cursor = tab.text_input.textCursor()
            line_number = tab.text_input.document().findBlock(cursor.position()).blockNumber()
            logging.debug(f"Character or space typed, updating line {line_number}")
            self.update_single_line(tab, line_number)
            if key == Qt.Key_Space:
                logging.debug("Space key detected, forcing line update")
                self.update_single_line(tab, line_number)
            return

        if key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = tab.text_input.textCursor()
            cursor_pos = cursor.position()
            text = tab.text_input.toPlainText()
            logging.debug(f"Before Enter - Cursor position: {cursor_pos}")
            cursor.insertText("\n")
            tab.original_text = tab.text_input.toPlainText()
            cursor.setPosition(cursor_pos + 1)
            tab.text_input.setTextCursor(cursor)
            tab.text_input.ensureCursorVisible()
            logging.debug(f"After Enter - Cursor position: {cursor_pos + 1}")
            line_number = tab.text_input.document().findBlock(cursor.position()).blockNumber()
            self.update_single_line(tab, line_number)
            self.is_typing = False
            return

        if key in (Qt.Key_Up, Qt.Key_Down, Qt.Key_Left, Qt.Key_Right):
            cursor = tab.text_input.textCursor()
            cursor_pos = cursor.position()
            logging.debug(f"Before arrow key {key} - Cursor position: {cursor_pos}")
            if key == Qt.Key_Up:
                cursor.movePosition(QTextCursor.Up)
            elif key == Qt.Key_Down:
                cursor.movePosition(QTextCursor.Down)
            elif key == Qt.Key_Left:
                cursor.movePosition(QTextCursor.Left)
            elif key == Qt.Key_Right:
                cursor.movePosition(QTextCursor.Right)
            tab.text_input.setTextCursor(cursor)
            tab.text_input.ensureCursorVisible()
            logging.debug(f"After arrow key {key} - Cursor position: {cursor.position()}")
            self.update_counters()
            return

        if event.modifiers() & Qt.ControlModifier:
            if key == Qt.Key_B:
                self.toggle_bold()
            elif key == Qt.Key_I:
                self.toggle_italic()
            elif key == Qt.Key_U:
                self.toggle_underline()
            elif key == Qt.Key_Plus:
                self.zoom_slider.setValue(self.zoom_slider.value() + 1)
                self.apply_zoom()
            elif key == Qt.Key_Minus:
                self.zoom_slider.setValue(self.zoom_slider.value() - 1)
                self.apply_zoom()

        if key == Qt.Key_F11:
            self.toggle_fullscreen()

        super().keyPressEvent(event)

    def update_single_line(self, tab, line_number):
        if not tab or getattr(tab, 'is_updating', False):
            logging.debug("update_single_line skipped: tab is None or is_updating")
            return

        tab.is_updating = True
        logging.debug(f"Updating single line: {line_number}")
        try:
            tab.text_input.blockSignals(True)
            tab.text_output.blockSignals(True)

            input_cursor = tab.text_input.textCursor()
            input_pos = input_cursor.position()
            logging.debug(f"update_single_line - Initial cursor position: {input_pos}")
            current_input_text = tab.text_input.toPlainText()
            lines = current_input_text.split('\n')
            
            if line_number < len(lines):
                line_text = lines[line_number]
                line_text = line_text.replace('\u00a0', ' ')
                line_text_normalized = re.sub(r'\s+', ' ', line_text)
                logging.debug(f"Original line text: {repr(line_text)}")
                logging.debug(f"Normalized line text: {repr(line_text_normalized)}")
                if " " in line_text:
                    space_positions = [i for i, char in enumerate(line_text) if char.isspace()]
                    for pos in space_positions:
                        char = line_text[pos]
                        logging.debug(f"Space at position {pos}: Unicode {ord(char):04x} ({repr(char)})")

                selected_table = self.table_combo.currentText()
                braille_lines = tab.text_output.toPlainText().split('\n')
                while len(braille_lines) <= line_number:
                    braille_lines.append("")
                
                if line_text_normalized.strip() and selected_table:
                    formatted_line = self.braille_engine.wrap_text_by_sentence(line_text_normalized, self.line_width)
                    logging.debug(f"Formatted line before Braille conversion: {repr(formatted_line)}")
                    braille_line = self.braille_engine.to_braille(formatted_line, self.available_tables[selected_table], self.line_width)
                    logging.debug(f"Converted line {line_number}: '{line_text_normalized}' -> '{braille_line}'")
                    braille_lines[line_number] = braille_line
                    if " " in line_text_normalized:
                        logging.debug(f"Space found in normalized line {line_number}: '{line_text_normalized}'. Forcing Braille update.")
                        formatted_line = self.braille_engine.wrap_text_by_sentence(line_text_normalized, self.line_width)
                        braille_line = self.braille_engine.to_braille(formatted_line, self.available_tables[selected_table], self.line_width)
                        braille_lines[line_number] = braille_line
                else:
                    braille_lines[line_number] = ""
                    logging.debug(f"Empty line {line_number}: no conversion")
                
                tab.text_output.setPlainText('\n'.join(braille_lines))
                tab.original_braille = tab.text_output.toPlainText()
                tab.original_text = current_input_text
                
                if not self.is_typing:
                    self._restore_cursor_position(tab.text_input, input_pos)
                    logging.debug(f"Restored cursor position after update_single_line: {input_pos}")
                else:
                    logging.debug("Skipping cursor restoration due to ongoing typing")
            
            self.update_counters()
        except Exception as e:
            logging.error(f"Erreur dans update_single_line : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la mise à jour de la ligne.")
        finally:
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            tab.is_updating = False

    def _end_typing(self):
        self.is_typing = False
        logging.debug("Typing ended, triggering conversion if needed")
        self.update_conversion()

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
        fmt = QTextCharFormat()
        fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
        cursor.mergeCharFormat(fmt)
        self.sync_text_areas(tab)
        self.update_counters()

    def apply_zoom(self):
        scale = self.zoom_slider.value() / 100.0
        self.zoom_label.setText(f"Zoom: {self.zoom_slider.value()}%")
        style = f"font-size: {int(14 * scale)}px;"
        toolbar_style = f"QToolButton {{ padding: {int(6 * scale)}px; }}"
        menu_style = f"QMenuBar {{ font-size: {int(12 * scale)}px; }}"
        if getattr(self, '_last_style', None) != (style, toolbar_style, menu_style):
            self.central_widget.setStyleSheet(style)
            self.toolbar.setStyleSheet(toolbar_style)
            self.menuBar().setStyleSheet(menu_style)
            self._last_style = (style, toolbar_style, menu_style)
        tab = self.tab_widget.currentWidget()
        if tab:
            font_size = int(self.base_font_size * scale)
            tab.text_input.setFont(QFont(self.current_font, font_size))
            tab.text_output.setFont(QFont(self.current_font, font_size))
            tab.reset_borders()
        self.update_line_width()
        self.update_conversion()

    def adjust_font_size(self):
        font_size = self.font_size_spin.value()
        self.base_font_size = font_size
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        cursor = tab.text_input.textCursor()
        if not cursor.hasSelection():
            cursor.select(QTextCursor.Document)
        fmt = QTextCharFormat()
        fmt.setFontPointSize(font_size)
        fmt.setFontFamily(self.current_font)
        cursor.mergeCharFormat(fmt)
        tab.text_input.setFont(QFont(self.current_font, font_size))
        tab.text_output.setFont(QFont(self.current_font, font_size))
        self.sync_text_areas(tab)
        self.font_size_spin.setValue(font_size)
        self.update_line_width()
        self.update_conversion()

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
        line_width, ok = QInputDialog.getInt(
            self,
            "Ajuster la largeur des lignes",
            "Entrez la largeur de ligne (caractères) :",
            self.line_width,
            5,
            120,
            1,
        )
        if ok:
            if line_width < 5:
                QMessageBox.warning(self, "Erreur", "La largeur de ligne doit être d'au moins 5 caractères.")
                self.line_width = 5
            else:
                self.line_width = line_width
            self.min_line_width = self.line_width
            self.line_width_label.setText(f"Largeur de ligne : {self.line_width} caractères")
            tab = self.tab_widget.currentWidget()
            if tab:
                current_text = tab.text_input.toPlainText()
                current_braille = tab.text_output.toPlainText()
                
                lines = current_text.split('\n')
                formatted_lines = [self.braille_engine.wrap_text_by_sentence(line, self.line_width) for line in lines]
                formatted_text = '\n'.join(formatted_lines)

                braille_lines = current_braille.split('\n')
                formatted_braille_lines = [self.braille_engine.wrap_text_by_sentence(line, self.line_width) for line in braille_lines]
                formatted_braille = '\n'.join(formatted_braille_lines)

                tab.text_input.setPlainText(formatted_text)
                tab.text_output.setPlainText(formatted_braille)
                tab.original_text = formatted_text
                tab.original_braille = formatted_braille

                tab.text_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
                tab.text_input.setLineWrapColumnOrWidth(self.line_width)
                tab.text_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
                tab.text_output.setLineWrapColumnOrWidth(self.line_width)

            self.update_conversion()
            self.status_bar.showMessage(
                f"Largeur des lignes ajustée à {self.line_width} caractères", 3000
            )
        else:
            self.status_bar.showMessage("Ajustement de la largeur annulé", 3000)

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
                block_format.setLineHeight(
                    spacing * 100, QTextBlockFormat.ProportionalHeight
                )
                cursor.setBlockFormat(block_format)
                tab.text_input.setTextCursor(cursor)
                cursor = tab.text_output.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setLineHeight(
                    spacing * 100, QTextBlockFormat.ProportionalHeight
                )
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
        self.zoom_slider.setValue(100)
        self.apply_zoom()

    def toggle_window_size(self):
        if self.isMaximized():
            self.showNormal()
            self.toggle_size_button.setIcon(self.safe_icon("icons/maximize.png"))
        else:
            self.showMaximized()
            self.toggle_size_button.setIcon(self.safe_icon("icons/restore.png"))
        self.update_line_width()
        self.update_conversion()

    def sync_text_areas(self, tab):
        if not tab or getattr(tab, 'is_updating', False) or self.is_typing:
            logging.debug("sync_text_areas skipped: tab is None, is_updating, or typing")
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
            last_change = current_input_text[max(0, input_pos-1):input_pos] if text_changed else ""
            is_minor_change = text_changed and last_change in (' ', '\n') and len(current_input_text.strip()) == len(tab.original_text.strip())

            if is_minor_change:
                tab.original_text = current_input_text
                if selected_table:
                    lines = current_input_text.split('\n')
                    braille_lines = []
                    for line in lines:
                        if line.strip():
                            formatted_line = self.braille_engine.wrap_text_by_sentence(line, self.line_width)
                            braille_line = self.braille_engine.to_braille(formatted_line, self.available_tables[selected_table], self.line_width)
                            braille_lines.append(braille_line)
                        else:
                            braille_lines.append("")
                    formatted_braille = '\n'.join(braille_lines)
                    tab.text_output.setPlainText(formatted_braille)
                    tab.original_braille = formatted_braille
                self._restore_cursor_position(tab.text_input, input_pos)
                self._restore_cursor_position(tab.text_output, output_pos)
            else:
                if text_changed:
                    logging.debug("Text changed, updating Braille")
                    if current_input_text and selected_table:
                        self._convert_to_braille(tab, current_input_text)
                        self._restore_cursor_position(tab.text_input, input_pos)
                    else:
                        tab.text_output.clear()
                        tab.original_text = ""
                        tab.original_braille = ""
                elif braille_changed:
                    logging.debug("Braille changed, updating Text")
                    if current_output_braille and selected_table:
                        self._convert_to_text(tab, current_output_braille)
                        self._restore_cursor_position(tab.text_output, output_pos)
                    else:
                        tab.text_input.clear()
                        tab.original_text = ""
                        tab.original_braille = ""

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
            formatted_lines = []
            braille_lines = []
            for line in lines:
                if line.strip():
                    formatted_line = self.braille_engine.wrap_text_by_sentence(line, self.line_width)
                    braille_line = self.braille_engine.to_braille(formatted_line, selected_table, self.line_width)
                    formatted_braille_line = self.braille_engine.wrap_text_by_sentence(braille_line, self.line_width)
                    formatted_lines.append(formatted_line)
                    braille_lines.append(formatted_braille_line)
                else:
                    formatted_lines.append("")
                    braille_lines.append("")
            formatted_text = '\n'.join(formatted_lines)
            formatted_braille = '\n'.join(braille_lines)
            tab.text_input.setPlainText(formatted_text)
            tab.text_output.setPlainText(formatted_braille)
            tab.original_text = formatted_text
            tab.original_braille = formatted_braille
        else:
            thread = BrailleConversionThread(self.braille_engine, current_input, selected_table, self.line_width)
            thread.conversion_done.connect(lambda t, ft, fb: self.on_conversion_done(tab, ft, fb))
            thread.start()
            tab._conversion_thread = thread

    def _convert_to_text(self, tab, current_braille):
        selected_table = self.available_tables[self.table_combo.currentText()]
        braille_lines = current_braille.split('\n')
        text_lines = []
        formatted_braille_lines = []
        for line in braille_lines:
            if line.strip():
                formatted_braille_line = self.braille_engine.wrap_text_by_sentence(line, self.line_width)
                text_line = self.braille_engine.from_braille(formatted_braille_line, selected_table)
                formatted_text_line = self.braille_engine.wrap_text_by_sentence(text_line, self.line_width)
                text_lines.append(formatted_text_line)
                formatted_braille_lines.append(formatted_braille_line)
            else:
                text_lines.append("")
                formatted_braille_lines.append("")
        formatted_text = '\n'.join(text_lines)
        formatted_braille = '\n'.join(formatted_braille_lines)
        tab.text_input.setPlainText(formatted_text)
        tab.text_output.setPlainText(formatted_braille)
        tab.original_text = formatted_text
        tab.original_braille = formatted_braille

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
        self.sync_text_areas(tab)
        self.update_counters()

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

            if file_path.endswith(".bfr"):
                tab.text_output.setPlainText(filtered_text)
                tab.original_braille = filtered_text
            else:
                tab.text_input.setPlainText(filtered_text)
                tab.original_text = filtered_text
                if filtered_text.strip():
                    selected_table = self.table_combo.currentText()
                    if selected_table:
                        try:
                            start_convert = time.time()
                            thread = BrailleConversionThread(self.braille_engine, filtered_text,
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
            tab.text_input.textChanged.connect(self.update_conversion)
            tab.text_output.textChanged.connect(self.update_conversion)

            tab_title = os.path.basename(file_path)
            self.tab_widget.addTab(tab, tab_title)
            if self.logged_in_user:
                try:
                    fichier = Fichier(tab_title, file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
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
            tab.text_input.textChanged.connect(self.update_conversion)
            tab.text_output.textChanged.connect(self.update_conversion)

            tab_title = os.path.basename(file_path)
            self.tab_widget.addTab(tab, tab_title)
            self.update_counters()
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            
            if self.logged_in_user:
                try:
                    fichier = Fichier(tab_title, file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
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
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
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
                        self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
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
            dialog.exec_()
            self.braille_engine.update_custom_table()
            self.update_conversion()
        except Exception as e:
            logging.error(f"Erreur lors de l'affichage de la table personnalisée : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'affichage de la table : {str(e)}")

    def show_usage_stats(self):
        if not self.logged_in_user:
            QMessageBox.warning(self, "Avertissement", "Veuillez vous connecter pour voir les statistiques.")
            return

        try:
            stats = self.db.get_usage_stats(self.logged_in_user.id)
            total_time = stats["total_usage_time"]
            files_processed = stats["files_processed"]
            print_jobs = stats["print_jobs"]

            hours = total_time // 3600
            minutes = (total_time % 3600) // 60
            seconds = total_time % 60

            message = (
                f"Statistiques d'utilisation pour {self.current_email}:\n\n"
                f"Temps total d'utilisation : {hours}h {minutes}m {seconds}s\n"
                f"Fichiers traités : {files_processed}\n"
                f"Impressions Braille : {print_jobs}"
            )
            QMessageBox.information(self, "Statistiques", message)
        except Exception as e:
            logging.error(f"Erreur lors de la récupération des statistiques : {str(e)}")
            QMessageBox.critical(self, "Erreur", f"Erreur lors de la récupération des statistiques : {str(e)}")

    def clear_text(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        tab.text_input.clear()
        tab.text_output.clear()
        tab.original_text = ""
        tab.original_braille = ""
        self.update_counters()

    def update_usage_time(self):
        if self.logged_in_user and hasattr(self, 'usage_start_time'):
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            try:
                self.db.update_usage_time(self.logged_in_user.id, elapsed)
            except Exception as e:
                logging.error(f"Erreur lors de la mise à jour du temps d'utilisation : {str(e)}")

    def update_counters(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        try:
            text = tab.text_input.toPlainText()
            lines = text.split("\n")
            line_count = len([line for line in lines if line.strip()])
            
            page_count = max(1, (line_count + self.lines_per_page - 1) // self.lines_per_page)
            
            words = re.findall(r'\b\w+\b', text)
            word_count = len(words)

            self.line_count.setText(str(line_count))
            self.page_count.setText(str(page_count))
            self.word_count.setText(str(word_count))

            cursor = tab.text_input.textCursor()
            line_number = tab.text_input.document().findBlock(cursor.position()).blockNumber() + 1
            tab_title = self.tab_widget.tabText(self.tab_widget.indexOf(tab))
            self.status_bar.showMessage(f"Ligne actuelle : {line_number} dans '{tab_title}'")
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour des compteurs : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la mise à jour des compteurs.")

    def update_line_width(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        try:
            tab.text_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
            tab.text_input.setLineWrapColumnOrWidth(self.line_width)
            tab.text_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
            tab.text_output.setLineWrapColumnOrWidth(self.line_width)
        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de la largeur de ligne : {str(e)}")
            self.status_bar.showMessage("Erreur lors de la mise à jour de la largeur de ligne.")

    def _get_cursor_position_info(self, text, cursor_pos):
        lines = text[:cursor_pos].split('\n')
        line = len(lines)
        col = len(lines[-1]) if lines else 0
        return (line, col)

    def _restore_cursor_position(self, text_edit, cursor_pos):
        logging.debug(f"Restoring cursor position to: {cursor_pos}")
        cursor = text_edit.textCursor()
        text = text_edit.toPlainText()
        valid_pos = min(cursor_pos, len(text))
        cursor.setPosition(valid_pos)
        text_edit.setTextCursor(cursor)
        text_edit.ensureCursorVisible()
        logging.debug(f"Cursor restored to: {valid_pos}")

    def update_conversion(self):
        tab = self.tab_widget.currentWidget()
        if not tab or getattr(tab, 'is_updating', False) or self.is_typing:
            logging.debug("update_conversion skipped: tab is None, is_updating, or typing")
            return
        logging.debug("Scheduling conversion update")
        self.conversion_timer.start(200)

    def _trigger_conversion(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            logging.debug("Triggering conversion")
            self.sync_text_areas(tab)
            self.update_counters()

    def handle_resize(self):
        self.update_line_width()
        self.update_conversion()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.resize_timer.start(100)

    def closeEvent(self, event):
        if self.logged_in_user and hasattr(self, 'usage_start_time'):
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    stderr_redirect = StderrToLog()
    sys.stderr = stderr_redirect
    window = BrailleUI(app)
    window.show()
    sys.exit(app.exec_())