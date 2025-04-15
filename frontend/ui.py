import os
import re
import shutil
import time
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QComboBox, QTabWidget, QFileDialog, QToolBar, QAction, QMessageBox,
    QStatusBar, QSlider, QMenuBar, QMenu, QSpinBox, QInputDialog, QLabel,
    QApplication, QSpacerItem, QSizePolicy, QProgressDialog
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
from frontend.braille_tab import BrailleTab
from frontend.styles import set_light_mode, set_dark_mode
from frontend.custom_table import CustomBrailleTableWidget
import pytesseract
from PIL import Image, ImageEnhance

# Configuration portable de Tesseract
pytesseract.pytesseract.tesseract_cmd = shutil.which("tesseract") or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
if not os.path.exists(pytesseract.pytesseract.tesseract_cmd):
    raise Exception("Tesseract-OCR n'est pas installé ou inaccessible.")

# Vérification des fichiers de langue
tessdata_dir = os.path.join(os.path.dirname(pytesseract.pytesseract.tesseract_cmd), "tessdata")
required_langs = ["fra", "ara"]
for lang in required_langs:
    if not os.path.exists(os.path.join(tessdata_dir, f"{lang}.traineddata")):
        print(f"Avertissement : Le fichier de langue '{lang}.traineddata' est manquant.")

# Thread pour la conversion Braille avec conversion partielle
class BrailleConversionThread(QThread):
    conversion_done = pyqtSignal(object, str, str)

    def __init__(self, braille_engine, text, table, line_width):
        super().__init__()
        self.braille_engine = braille_engine
        self.text = text
        self.table = table
        self.line_width = line_width
        self.full_text = text
        self.limit = 1000  # Limite initiale pour la conversion rapide

    def run(self):
        start_convert = time.time()
        
        # Convertir uniquement une partie du texte pour un affichage rapide
        text_to_convert = self.text[:self.limit] if len(self.text) > self.limit else self.text
        formatted_text = self.braille_engine.wrap_text_plain(text_to_convert, self.line_width)
        braille_text = self.braille_engine.to_braille(formatted_text, self.table, self.line_width)
        formatted_braille = self.braille_engine.wrap_text(braille_text, self.line_width)
        
        # Indiquer si le texte est tronqué
        if len(self.text) > self.limit:
            formatted_text += "\n[... Texte tronqué, conversion en cours...]"
            formatted_braille += "\n[... Braille tronqué, conversion en cours...]"
        
        convert_time = time.time() - start_convert
        print(f"Temps de conversion initiale en Braille: {convert_time:.2f} secondes")
        self.conversion_done.emit(self, formatted_text, formatted_braille)
        
        # Si plus de texte à convertir, lancer une conversion complète en arrière-plan
        if len(self.text) > self.limit:
            start_full_convert = time.time()
            full_formatted_text = self.braille_engine.wrap_text_plain(self.full_text, self.line_width)
            full_braille_text = self.braille_engine.to_braille(full_formatted_text, self.table, self.line_width)
            full_formatted_braille = self.braille_engine.wrap_text(full_braille_text, self.line_width)
            full_convert_time = time.time() - start_full_convert
            print(f"Temps de conversion complète en Braille: {full_convert_time:.2f} secondes")
            self.conversion_done.emit(self, full_formatted_text, full_formatted_braille)

class BrailleUI(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Convertisseur Texte ↔ Braille")
        self.setGeometry(100, 100, 1050, 600)
        self.initial_size = QSize(1000, 600)

        self.braille_engine = BrailleEngine()
        self.file_handler = FileHandler()
        self.file_handler.parent = self
        self.db = Database()
        self.available_tables = self.braille_engine.get_available_tables()

        self.dark_mode = False
        self.conversion_mode = "text_to_braille"
        self.line_width = 80
        self.min_line_width = 40
        self.lines_per_page = 25
        self.update_timer = QTimer()
        self.delay_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_conversion)
        self.resize_timer = QTimer()
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self.handle_resize)
        self.logged_in_user = None
        self.current_email = None
        self.usage_timer = QTimer()
        self.usage_timer.timeout.connect(self.update_usage_time)
        self.usage_timer.start(1000)
        self.zoom_debounce_timer = QTimer()
        self.zoom_debounce_timer.setSingleShot(True)
        self.zoom_debounce_timer.timeout.connect(self.apply_zoom)

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

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.title_label = QLabel("Convertisseur Texte ↔ Braille")
        self.title_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.main_layout.addWidget(self.title_label)

        table_layout = QHBoxLayout()
        self.table_combo_label = QLabel("Langue (Table) :")
        self.table_combo = QComboBox()
        self.table_combo.addItems(self.available_tables.keys())
        self.table_combo.setCurrentText("Français (Grade 1)")
        self.table_combo.currentTextChanged.connect(self.debounce_update)
        table_layout.addWidget(self.table_combo_label)
        table_layout.addWidget(self.table_combo)
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
        self.zoom_label = QLabel("Zoom Interface: 100%")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(50)
        self.zoom_slider.setMaximum(200)
        self.zoom_slider.setValue(100)
        self.zoom_slider.valueChanged.connect(self.debounce_zoom)
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

        self.stack_layout.addWidget(self.main_widget)

        self.init_status_bar()

        self.auth_container.hide()
        self.main_widget.show()
        self.new_document()

        self.init_menu_bar()
        self.toolbar = self.addToolBar("Main Toolbar")
        self.init_toolbar()

        set_light_mode(self.app)
        self.auth_widget.check_device_auth()

    def safe_icon(self, path):
        """Retourne une icône si le fichier existe, sinon une icône vide."""
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
        reverse_action = QAction("Inverser la conversion", self)
        reverse_action.setShortcut("Ctrl+R")
        reverse_action.triggered.connect(self.reverse_conversion)
        edit_menu.addAction(reverse_action)
        edit_menu.addAction("Effacer le texte", self.clear_text)

        translate_action = QAction("Traduire en Braille", self)
        translate_action.setShortcut("Ctrl+T")
        translate_action.triggered.connect(self.update_conversion)
        edit_menu.addAction(translate_action)

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
            ("icons/bold.png", "Gras", self.toggle_bold, ""),
            ("icons/italic.png", "Italique", self.toggle_italic, ""),
            ("icons/souligne.png", "Souligné", self.toggle_underline, ""),
            ("icons/align-left.png", "Aligner à gauche", lambda: self.align_text(Qt.AlignLeft), ""),
            ("icons/align-center.png", "Aligner au centre", lambda: self.align_text(Qt.AlignCenter), ""),
            ("icons/align-right.png", "Aligner à droite", lambda: self.align_text(Qt.AlignRight), ""),
            ("icons/reverse.png", "Inverser", self.reverse_conversion, "")
        ]
        for icon_path, tooltip, callback, attr_name in icons:
            action = self.toolbar.addAction(self.safe_icon(icon_path), tooltip, callback)
            if attr_name:
                setattr(self, attr_name, action)

        self.toolbar.addSeparator()
        self.toolbar.addWidget(QLabel("Taille Police : "))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(8)
        self.font_size_spin.setMaximum(50)
        self.font_size_spin.setValue(18)
        self.font_size_spin.valueChanged.connect(self.adjust_font_size)
        self.toolbar.addWidget(self.font_size_spin)

        # Ajouter un espaceur pour pousser le bouton d'authentification à droite
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.toolbar.addWidget(spacer)

        # Ajouter le bouton d'authentification à droite
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

    def keyPressEvent(self, event):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return

        modifiers = event.modifiers()
        key = event.key()

        if modifiers & Qt.ControlModifier:
            if key == Qt.Key_B:
                self.toggle_bold()
            elif key == Qt.Key_I:
                self.toggle_italic()
            elif key == Qt.Key_U:
                self.toggle_underline()
            elif key == Qt.Key_Plus:
                self.zoom_slider.setValue(self.zoom_slider.value() + 10)
                self.debounce_zoom()
            elif key == Qt.Key_Minus:
                self.zoom_slider.setValue(self.zoom_slider.value() - 10)
                self.debounce_zoom()

        if key == Qt.Key_F11:
            self.toggle_fullscreen()

        super().keyPressEvent(event)

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
        if tab:
            cursor = tab.text_input.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontWeight(QFont.Bold if not cursor.charFormat().fontWeight() == QFont.Bold else QFont.Normal)
            cursor.mergeCharFormat(fmt)
            self.sync_text_areas(tab)
            self.update_counters()

    def toggle_italic(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            cursor = tab.text_input.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontItalic(not cursor.charFormat().fontItalic())
            cursor.mergeCharFormat(fmt)
            self.sync_text_areas(tab)
            self.update_counters()

    def toggle_underline(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            cursor = tab.text_input.textCursor()
            fmt = QTextCharFormat()
            fmt.setFontUnderline(not cursor.charFormat().fontUnderline())
            cursor.mergeCharFormat(fmt)
            self.sync_text_areas(tab)
            self.update_counters()

    def debounce_zoom(self):
        self.zoom_debounce_timer.start(100)

    def apply_zoom(self):
        scale = self.zoom_slider.value() / 100.0
        self.zoom_label.setText(f"Zoom Interface: {self.zoom_slider.value()}%")
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
            tab.text_input.setStyleSheet("")
            tab.text_output.setStyleSheet("")
        self.update_line_width()
        self.update_conversion()

    def adjust_font_size(self):
        font_size = self.font_size_spin.value()
        tab = self.tab_widget.currentWidget()
        if tab:
            cursor = tab.text_input.textCursor()
            if not cursor.hasSelection():
                cursor.select(QTextCursor.Document)
            fmt = QTextCharFormat()
            fmt.setFontPointSize(font_size)
            cursor.mergeCharFormat(fmt)
            tab.text_input.setFont(QFont(BRAILLE_FONT_NAME, font_size))
            tab.text_output.setFont(QFont(BRAILLE_FONT_NAME, font_size))
            self.sync_text_areas(tab)
        self.font_size_spin.setValue(font_size)
        self.update_line_width()
        self.update_conversion()

    def align_text(self, alignment):
        tab = self.tab_widget.currentWidget()
        if tab:
            cursor = tab.text_input.textCursor()
            if not cursor.hasSelection():
                cursor.select(QTextCursor.BlockUnderCursor)
            block_format = cursor.blockFormat()
            block_format.setAlignment(alignment)
            cursor.setBlockFormat(block_format)
            self.sync_text_areas(tab)
            self.update_counters()

    def adjust_line_width(self):
        line_width, ok = QInputDialog.getInt(self, "Ajuster la largeur des lignes",
                                             "Entrez la largeur de ligne (caractères) :",
                                             self.line_width, 20, 120, 1)
        if ok:
            self.min_line_width = line_width
            self.update_line_width()
            self.update_conversion()

    def adjust_lines_per_page(self):
        lines_per_page, ok = QInputDialog.getInt(self, "Nombre de lignes par page",
                                                 "Entrez le nombre maximum de lignes par page :",
                                                 self.lines_per_page, 10, 100, 1)
        if ok:
            self.lines_per_page = lines_per_page
            self.update_conversion()

    def adjust_line_spacing(self):
        spacing, ok = QInputDialog.getDouble(self, "Interligne", "Entrez l'espacement (1.0 par défaut) :", 1.0, 0.5, 3.0, 1)
        if ok:
            tab = self.tab_widget.currentWidget()
            if tab:
                cursor = tab.text_input.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setLineHeight(spacing * 100, QTextBlockFormat.ProportionalHeight)
                cursor.setBlockFormat(block_format)
                self.sync_text_areas(tab)

    def adjust_indent(self):
        indent, ok = QInputDialog.getInt(self, "Retrait", "Entrez le retrait (mm) :", 0, 0, 50, 1)
        if ok:
            tab = self.tab_widget.currentWidget()
            if tab:
                cursor = tab.text_input.textCursor()
                if not cursor.hasSelection():
                    cursor.select(QTextCursor.Document)
                block_format = cursor.blockFormat()
                block_format.setTextIndent(indent)
                cursor.setBlockFormat(block_format)
                self.sync_text_areas(tab)

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

    def debounce_update(self):
        self.update_timer.start(100)

    def update_conversion(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            self.sync_text_areas(tab)
            self.update_counters()
            tab.validate_conversion()

    def sync_text_areas(self, tab):
        if not tab:
            return

        if tab.file_path and tab.file_path.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.tiff')):
            return

        self._set_text_direction(tab)
        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)

        current_input = tab.text_input.toPlainText().strip()
        cursor = tab.text_input.textCursor()
        cursor_position = cursor.position()

        if self.conversion_mode == "text_to_braille":
            self._convert_to_braille(tab, current_input, cursor, cursor_position)
        else:
            self._convert_to_text(tab, current_input, cursor, cursor_position)

        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)

    def _set_text_direction(self, tab):
        direction = Qt.RightToLeft if "Arabe" in self.table_combo.currentText() else Qt.LeftToRight
        tab.text_input.setLayoutDirection(direction)
        tab.text_output.setLayoutDirection(direction)

    def _convert_to_braille(self, tab, current_input, cursor, cursor_position):
        if not tab.original_braille or current_input != tab.original_text:
            selected_table = self.table_combo.currentText()
            if not (current_input and selected_table):
                tab.text_output.clear()
                tab.original_text = ""
                tab.original_braille = ""
                return

            formatted_text = self.braille_engine.wrap_text_plain(current_input, self.line_width)
            if formatted_text != tab.text_input.toPlainText():
                tab.text_input.setPlainText(formatted_text)
                cursor.setPosition(min(cursor_position, len(formatted_text)))
                tab.text_input.setTextCursor(cursor)

            braille_text = self.braille_engine.to_braille(formatted_text, self.available_tables[selected_table], self.line_width)
            formatted_braille = self.braille_engine.wrap_text(braille_text, self.line_width)
            tab.text_output.setPlainText(formatted_braille)
            tab.original_text = formatted_text
            tab.original_braille = formatted_braille
        else:
            tab.text_output.setPlainText(tab.original_braille)
            cursor.setPosition(cursor_position)
            tab.text_input.setTextCursor(cursor)

    def _convert_to_text(self, tab, current_input, cursor, cursor_position):
        if not tab.original_text or current_input != tab.original_braille:
            selected_table = self.table_combo.currentText()
            if not (current_input and selected_table):
                tab.text_output.clear()
                tab.original_text = ""
                tab.original_braille = ""
                return

            formatted_braille = self.braille_engine.wrap_text(current_input, self.line_width)
            if formatted_braille != tab.text_input.toPlainText():
                tab.text_input.setPlainText(formatted_braille)
                cursor.setPosition(min(cursor_position, len(formatted_braille)))
                tab.text_input.setTextCursor(cursor)

            text = self.braille_engine.from_braille(formatted_braille, self.available_tables[selected_table])
            formatted_text = self.braille_engine.wrap_text_plain(text, self.line_width)
            tab.text_output.setPlainText(formatted_text)
            tab.original_text = formatted_text
            tab.original_braille = formatted_braille
        else:
            tab.text_output.setPlainText(tab.original_text)
            cursor.setPosition(cursor_position)
            tab.text_input.setTextCursor(cursor)

    def test_conversion(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return
        
        tests = {
            "Français (Grade 1)": "Voici la version mise à jour, intégrant l’analyse",
            "Arabe (Grade 1)": "مرحبا بالعالم",
            "Anglais (Grade 1)": "Hello World",
            "Anglais (Grade 2)": "Hello World",
            "Français (Grade 2)": "Bonjour le monde"
        }
        
        selected_table = self.table_combo.currentText()
        test_text = tests.get(selected_table, "Test text")
        
        tab.text_input.setPlainText(test_text)
        self.update_conversion()

    def reverse_conversion(self):
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
                    formatted_text = self.braille_engine.wrap_text_plain(text, self.line_width)
                    tab.text_output.setPlainText(formatted_text)
                else:
                    tab.text_output.clear()
            else:
                self.conversion_mode = "text_to_braille"
                tab.text_input_label.setText("Texte :")
                tab.text_output_label.setText("Braille :")
                tab.text_input.setPlainText(tab.original_text)
                braille_text = self.braille_engine.to_braille(tab.original_text, self.available_tables[self.table_combo.currentText()], self.line_width)
                formatted_braille = self.braille_engine.wrap_text(braille_text, self.line_width)
                tab.text_output.setPlainText(formatted_braille)
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)
            self.update_counters()

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            set_dark_mode(self.app)
            self.dark_mode_action.setIcon(self.safe_icon("icons/moon.png"))
        else:
            set_light_mode(self.app)
            self.dark_mode_action.setIcon(self.safe_icon("icons/sun.png"))

    def new_document(self):
        tab = BrailleTab(self, save_type="Texte + Braille")
        tab_count = self.tab_widget.count() + 1
        default_title = f"Document sans titre {tab_count}"
        self.tab_widget.addTab(tab, default_title)
        self.tab_widget.setCurrentWidget(tab)
        self.sync_text_areas(tab)
        self.update_counters()

    def close_tab(self, index):
        tab = self.tab_widget.widget(index)
        if tab and (tab.text_input.toPlainText().strip() or tab.text_output.toPlainText().strip()):
            reply = QMessageBox.question(
                self, "Confirmer", "Voulez-vous fermer cet onglet ? Les modifications non sauvegardées seront perdues.",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return
        self.tab_widget.removeTab(index)

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
            text = self.file_handler.extract_text(file_path, max_pages=10)
            extract_time = time.time() - start_extract
            print(f"Temps d'extraction pour {file_path}: {extract_time:.2f} secondes")

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
                        start_convert = time.time()
                        thread = BrailleConversionThread(self.braille_engine, filtered_text,
                                                        self.available_tables[selected_table], self.line_width)
                        thread.conversion_done.connect(lambda _, ft, fb, t=tab: self.on_conversion_done(t, ft, fb))
                        thread.start()
                        tab._conversion_thread = thread
                        print(f"Démarrage de la conversion pour {file_path}...")
                    else:
                        tab.text_output.clear()
                else:
                    tab.text_output.clear()

            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)

            tab_title = os.path.basename(file_path) if file_path else "Document importé"
            self.tab_widget.addTab(tab, tab_title)
            if self.logged_in_user:
                fichier = Fichier(tab_title, file_path)
                self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)

        progress.setValue(len(file_paths))
        progress.close()
        if file_paths:
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            self.update_counters()

    def on_conversion_done(self, tab, formatted_text, formatted_braille):
        start_display = time.time()
        
        display_limit = 1000
        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)
        
        if len(formatted_text) > display_limit:
            tab.text_input.setPlainText(formatted_text[:display_limit] + "\n[... Chargement...]")
        else:
            tab.text_input.setPlainText(formatted_text)
            
        if len(formatted_braille) > display_limit:
            tab.text_output.setPlainText(formatted_braille[:display_limit] + "\n[... Chargement...]")
        else:
            tab.text_output.setPlainText(formatted_braille)
        
        tab.original_text = formatted_text
        tab.original_braille = formatted_braille
        
        QTimer.singleShot(100, lambda: self._complete_display(tab, formatted_text, formatted_braille))
        
        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)
        
        display_time = time.time() - start_display
        print(f"Temps d'affichage initial pour le texte et Braille: {display_time:.2f} secondes")

    def _complete_display(self, tab, full_text, full_braille):
        start_complete = time.time()
        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)
        tab.text_input.setPlainText(full_text)
        tab.text_output.setPlainText(full_braille)
        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)
        complete_time = time.time() - start_complete
        print(f"Temps d'affichage complet pour le texte et Braille: {complete_time:.2f} secondes")

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
            
            tab.text_input.blockSignals(False)
            tab.text_output.blockSignals(False)

            tab_title = os.path.basename(file_path)
            self.tab_widget.addTab(tab, tab_title)
            self.update_counters()
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            
            if self.logged_in_user:
                fichier = Fichier(tab_title, file_path)
                self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
                
        except Exception as e:
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
                "docx": "Fichiers Word (*.docx)"
            }
            file_path, _ = QFileDialog.getSaveFileName(self, f"Enregistrer sous {export_format.upper()}", "", filters[export_format])
            if not file_path:
                return False

        try:
            if export_format == "pdf":
                self.file_handler.export_pdf(file_path, tab.text_input.document(), tab.text_output.toPlainText(), save_type)
            elif export_format == "docx":
                self.file_handler.export_docx(file_path, tab.text_input.document(), tab.text_output.toPlainText(), save_type)
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
            self.tab_widget.setTabText(self.tab_widget.indexOf(tab), os.path.basename(file_path))
            QMessageBox.information(self, "Succès", f"Fichier sauvegardé : {file_path}")

            if self.logged_in_user:
                fichier = Fichier(os.path.basename(file_path), file_path)
                self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            return True

        except Exception as e:
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
                QMessageBox.information(self, "Succès", f"Texte Braille sauvegardé dans {file_path}")
                if self.logged_in_user:
                    fichier = Fichier(os.path.basename(file_path), file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")

    def export_to_pdf(self):
        self._save_or_export(self.tab_widget.currentWidget(), export_format="pdf")

    def export_to_word(self):
        self._save_or_export(self.tab_widget.currentWidget(), export_format="docx")

    def export_to_gcode(self):
        tab = self.tab_widget.currentWidget()
        if not tab or not hasattr(self.file_handler, 'last_gcode') or self.file_handler.last_gcode is None:
            QMessageBox.warning(self, "Avertissement", "Aucune image importée ou convertie pour générer du Gcode.")
            return
        file_path, _ = QFileDialog.getSaveFileName(self, "Exporter en Gcode", "", "Fichiers Gcode (*.gcode)")
        if file_path:
            if self.file_handler.export_to_gcode(file_path):
                QMessageBox.information(self, "Succès", f"Gcode exporté vers {file_path}")
                if self.logged_in_user:
                    fichier = Fichier(os.path.basename(file_path), file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            else:
                QMessageBox.critical(self, "Erreur", "Erreur lors de l'exportation du Gcode.")

    def print_braille(self):
        tab = self.tab_widget.currentWidget()
        if not tab or not tab.text_output.toPlainText().strip():
            QMessageBox.warning(self, "Avertissement", "Aucun texte Braille à imprimer.")
            return
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPrinter.A4)
        printer.setPageMargins(10, 10, 10, 10, QPrinter.Millimeter)
        dialog = QPrintDialog(printer, self)
        if dialog.exec_() == QPrintDialog.Accepted:
            if self.file_handler.print_content(printer, tab.text_input.toPlainText(), tab.text_output.toPlainText()):
                QMessageBox.information(self, "Succès", "Impression terminée.")
                if self.logged_in_user:
                    impression = Impression(tab.text_input.toPlainText(), printer.printerName())
                    self.db.ajouter_impression(self.logged_in_user.id, impression)
            else:
                QMessageBox.critical(self, "Erreur", "Erreur lors de l'impression.")

    def update_counters(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            self.page_count.setText("Texte: 0 | Braille: 0")
            self.line_count.setText("0")
            self.word_count.setText("0")
            self.status_bar.showMessage("Aucun onglet ouvert")
            return

        text = tab.text_input.toPlainText().strip()
        braille = tab.text_output.toPlainText().strip()

        if hasattr(tab, "last_text") and tab.last_text == text and hasattr(tab, "last_braille") and tab.last_braille == braille:
            return

        lines = text.count('\n') + 1 if text else 0
        words = len(re.findall(r'\b\w+\b', text, re.UNICODE)) if text else 0
        chars_per_page = 3000
        num_pages = max(1, len(text) // chars_per_page + 1)
        braille_lines = braille.count('\n') + 1 if braille else 0
        braille_pages = max(1, braille_lines // self.lines_per_page + 1)
        braille_chars = len([c for c in braille if '\u2800' <= c <= '\u28FF']) if braille else 0

        self.page_count.setText(f"Texte: {num_pages} | Braille: {braille_pages}")
        self.line_count.setText(str(lines))
        self.word_count.setText(str(words))
        self.status_bar.showMessage(f"Caractères Braille : {braille_chars}")

        tab.last_text = text
        tab.last_braille = braille

    def update_usage_time(self):
        if self.logged_in_user and hasattr(self, 'usage_start_time'):
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.status_bar.showMessage(f"Temps d'utilisation : {elapsed // 60} min {elapsed % 60} sec")

    def show_usage_stats(self):
        if self.logged_in_user:
            stats = self.db.get_usage_stats(self.logged_in_user.id)
            msg = f"Durée totale : {stats['total_usage_time'] // 60} min\n"
            msg += f"Textes créés : {stats['text_count']}\n"
            msg += f"Impressions : {stats['print_count']}\n"
            msg += "Fichiers par type :\n" + "\n".join(f"{k}: {v}" for k, v in stats['file_stats'].items())
            QMessageBox.information(self, "Statistiques", msg)

    def show_custom_table(self):
        self.custom_table_widget = CustomBrailleTableWidget(self)
        self.stack_layout.addWidget(self.custom_table_widget)
        self.custom_table_widget.show()

    def clear_text(self):
        tab = self.tab_widget.currentWidget()
        if tab and (tab.text_input.toPlainText().strip() or tab.text_output.toPlainText().strip()):
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

    def update_line_width(self):
        tab = self.tab_widget.currentWidget()
        if not tab:
            return False

        text_input = tab.text_input
        text_output = tab.text_output

        input_margins = text_input.contentsMargins()
        output_margins = text_output.contentsMargins()
        input_width = text_input.viewport().width() - input_margins.left() - input_margins.right()
        output_width = text_output.viewport().width() - output_margins.left() - output_margins.right()

        font_metrics = text_input.fontMetrics()
        char_width = font_metrics.averageCharWidth()

        chars = max(self.min_line_width, min((input_width // char_width) - 2, (output_width // char_width) - 2))

        if abs(self.line_width - chars) > 5:
            self.line_width = chars
            return True
        return False

    def handle_resize(self):
        if self.update_line_width():
            self.update_conversion()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.initial_size = self.size()
        self.resize_timer.start(100)

    def closeEvent(self, event):
        if self.logged_in_user and hasattr(self, 'usage_start_time'):
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        self.db.fermer_connexion()
        event.accept()

if __name__ == "__main__":
    app = QApplication([])
    window = BrailleUI(app)
    window.show()
    app.exec_()