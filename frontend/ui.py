import os
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton,
    QComboBox, QTabWidget, QFileDialog, QToolBar, QAction, QMessageBox,
    QStatusBar, QSlider, QMenuBar, QMenu, QSpinBox, QInputDialog, QLabel, QApplication
)
from PyQt5.QtCore import Qt, QTimer, QEvent, QTime
from PyQt5.QtGui import QIcon, QFont, QTextCharFormat, QTextCursor, QTextBlockFormat
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

pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'

if not os.path.exists(r'C:\Program Files\Tesseract-OCR\tessdata\fra.traineddata'):
    raise Exception("Le fichier de langue 'fra.traineddata' est manquant.")

class BrailleUI(QMainWindow):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowTitle("Convertisseur Texte ↔ Braille")
        self.setGeometry(100, 100, 1000, 600)

        self.braille_engine = BrailleEngine()
        self.file_handler = FileHandler()
        self.file_handler.parent = self
        self.db = Database()
        self.available_tables = self.braille_engine.get_available_tables()

        self.dark_mode = False
        self.conversion_mode = "text_to_braille"
        self.line_width = 33
        self.lines_per_page = 25
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_conversion)
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
        self.stack_layout.setAlignment(Qt.AlignCenter)

        self.auth_widget = AuthWidget(self)
        self.auth_widget.logout_signal.connect(self.handle_logout)
        self.stack_layout.addWidget(self.auth_widget)

        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)

        self.title_label = QLabel("Convertisseur Texte ↔ Braille")
        self.title_label.setFont(QFont("Arial", 24, QFont.Bold))
        self.main_layout.addWidget(self.title_label)

        table_layout = QHBoxLayout()
        self.table_combo_label = QLabel("Langue (Table) :")
        self.table_combo = QComboBox()
        self.table_combo.addItems(self.available_tables.keys())
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
        self.zoom_slider.valueChanged.connect(self.adjust_interface_zoom)
        self.reset_zoom_button = QPushButton("Réinitialiser Zoom")
        self.reset_zoom_button.clicked.connect(self.reset_zoom)
        self.toggle_size_button = QPushButton()
        self.toggle_size_button.setIcon(QIcon("icons/maximize.png"))
        self.toggle_size_button.clicked.connect(self.toggle_window_size)
        zoom_layout.addStretch()
        zoom_layout.addWidget(self.zoom_label)
        zoom_layout.addWidget(self.zoom_slider)
        zoom_layout.addWidget(self.reset_zoom_button)
        zoom_layout.addWidget(self.toggle_size_button)
        control_layout.addLayout(zoom_layout)
        self.main_layout.addLayout(control_layout)

        auth_layout = QHBoxLayout()
        self.auth_button = QPushButton()
        self.auth_button.setIcon(QIcon("icons/user.png"))
        self.auth_button.setText("Se connecter")
        self.auth_button.setToolTip("Se connecter")
        self.auth_button.clicked.connect(self.show_auth_widget)
        auth_layout.addStretch()
        auth_layout.addWidget(self.auth_button)
        self.main_layout.addLayout(auth_layout)

        self.stack_layout.addWidget(self.main_widget)
        self.auth_widget.show()  # Afficher l'authentification par défaut
        self.main_widget.hide()

        self.init_status_bar()
        self.init_menu_bar()
        self.toolbar = self.addToolBar("Main Toolbar")
        self.init_toolbar()
        set_light_mode(self.app)
        self.auth_widget.check_device_auth()

    def show_auth_widget(self):
        self.main_widget.hide()
        self.auth_widget.show()

    def show_main_interface(self, email, user_info):
        self.logged_in_user = self.db.get_utilisateur_by_email(email)
        if not self.logged_in_user:
            user_id = self.db.ajouter_utilisateur(user_info.get("nom", email.split("@")[0]), email)
            self.logged_in_user = self.db.get_utilisateur_by_email(email)
        self.current_email = email
        self.auth_widget.hide()
        self.main_widget.show()
        self.auth_button.setIcon(QIcon("icons/user-logged-in.png"))
        self.auth_button.setText(f"{email}")
        self.auth_button.setToolTip(f"Connecté : {email}")
        self.new_document()
        self.usage_start_time = QTime.currentTime()

    def handle_logout(self):
        if self.logged_in_user:
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        self.logged_in_user = None
        self.current_email = None
        self.main_widget.hide()
        self.auth_widget.show()
        self.auth_widget.logged_in_event()
        self.auth_button.setIcon(QIcon("icons/user.png"))
        self.auth_button.setText("Se connecter")
        self.auth_button.setToolTip("Se connecter")

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
        self.toolbar.addAction(QIcon("icons/new.png"), "Nouveau", self.new_document)
        self.toolbar.addAction(QIcon("icons/open.png"), "Ouvrir", self.import_files)
        self.toolbar.addAction(QIcon("icons/image.png"), "Ouvrir une image", self.import_image)
        self.toolbar.addAction(QIcon("icons/save.png"), "Sauvegarder", self.save_document)
        self.toolbar.addAction(QIcon("icons/save_as.png"), "Enregistrer sous", self.save_document_as)
        self.toolbar.addAction(QIcon("icons/braille.png"), "Sauvegarder le Braille", self.save_braille_text)
        self.toolbar.addAction(QIcon("icons/pdf.png"), "Exporter en PDF", self.export_to_pdf)
        self.toolbar.addAction(QIcon("icons/word.png"), "Exporter en Word", self.export_to_word)
        self.toolbar.addAction(QIcon("icons/braille_print.png"), "Imprimer en Braille", self.print_braille)
        self.dark_mode_action = self.toolbar.addAction(QIcon("icons/sun.png"), "Mode Sombre", self.toggle_dark_mode)
        self.toolbar.addSeparator()

        self.toolbar.addAction(QIcon("icons/bold.png"), "Gras", self.toggle_bold)
        self.toolbar.addAction(QIcon("icons/italic.png"), "Italique", self.toggle_italic)
        self.toolbar.addAction(QIcon("icons/souligne.png"), "Souligné", self.toggle_underline)
        self.toolbar.addWidget(QLabel("Taille Police : "))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setMinimum(8)
        self.font_size_spin.setMaximum(50)
        self.font_size_spin.setValue(18)
        self.font_size_spin.valueChanged.connect(self.adjust_font_size)
        self.toolbar.addWidget(self.font_size_spin)

        self.toolbar.addAction(QIcon("icons/align-left.png"), "Aligner à gauche", lambda: self.align_text(Qt.AlignLeft))
        self.toolbar.addAction(QIcon("icons/align-center.png"), "Aligner au centre", lambda: self.align_text(Qt.AlignCenter))
        self.toolbar.addAction(QIcon("icons/align-right.png"), "Aligner à droite", lambda: self.align_text(Qt.AlignRight))

        self.toolbar.addSeparator()
        self.toolbar.addAction(QIcon("icons/reverse.png"), "Inverser", self.reverse_conversion)

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
                self.adjust_interface_zoom()
            elif key == Qt.Key_Minus:
                self.zoom_slider.setValue(self.zoom_slider.value() - 10)
                self.adjust_interface_zoom()

        if key == Qt.Key_F11:
            self.toggle_fullscreen()

        super().keyPressEvent(event)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.toggle_size_button.setIcon(QIcon("icons/maximize.png"))
        else:
            self.showFullScreen()
            self.toggle_size_button.setIcon(QIcon("icons/restore.png"))

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

    def adjust_interface_zoom(self):
        scale = self.zoom_slider.value() / 100.0
        self.zoom_label.setText(f"Zoom Interface: {self.zoom_slider.value()}%")
        self.central_widget.setStyleSheet(f"font-size: {int(14 * scale)}px;")
        self.toolbar.setStyleSheet(f"QToolButton {{ padding: {int(6 * scale)}px; }}")
        self.menuBar().setStyleSheet(f"QMenuBar {{ font-size: {int(12 * scale)}px; }}")
        for i in range(self.tab_widget.count()):
            tab = self.tab_widget.widget(i)
            tab.text_input.setStyleSheet("")
            tab.text_output.setStyleSheet("")

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
                                             self.line_width, 1, 33, 1)
        if ok:
            self.line_width = line_width
            self.update_conversion()

    def adjust_lines_per_page(self):
        lines_per_page, ok = QInputDialog.getInt(self, "Nombre de lignes par page",
                                                 "Entrez le nombre maximum de lignes par page :",
                                                 self.lines_per_page, 1, 100, 1)
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
        self.adjust_interface_zoom()

    def toggle_window_size(self):
        if self.isMaximized():
            self.showNormal()
            self.toggle_size_button.setIcon(QIcon("icons/maximize.png"))
        else:
            self.showMaximized()
            self.toggle_size_button.setIcon(QIcon("icons/restore.png"))

    def debounce_update(self):
        self.update_timer.start(300)

    def update_conversion(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            self.sync_text_areas(tab)
            self.update_counters()

    def sync_text_areas(self, tab):
        if not tab:
            return
        tab.text_input.blockSignals(True)
        tab.text_output.blockSignals(True)
        if self.conversion_mode == "text_to_braille":
            text = tab.text_input.toPlainText().strip()
            selected_table = self.table_combo.currentText()
            if text and selected_table:
                braille_text = self.braille_engine.to_braille(text, self.available_tables[selected_table], self.line_width)
                tab.text_output.setPlainText(braille_text)
                tab.original_text = text
                tab.original_braille = braille_text
            else:
                tab.text_output.clear()
                tab.original_text = ""
                tab.original_braille = ""
        else:
            braille_text = tab.text_input.toPlainText().strip()
            selected_table = self.table_combo.currentText()
            if braille_text and selected_table:
                text = self.braille_engine.from_braille(braille_text, self.available_tables[selected_table])
                tab.text_output.setPlainText(text)
                tab.original_text = text
                tab.original_braille = braille_text
            else:
                tab.text_output.clear()
                tab.original_text = ""
                tab.original_braille = ""
        tab.text_input.blockSignals(False)
        tab.text_output.blockSignals(False)

    def on_text_changed(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            self.sync_text_areas(tab)
            self.update_counters()

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

    def toggle_dark_mode(self):
        self.dark_mode = not self.dark_mode
        if self.dark_mode:
            set_dark_mode(self.app)
            self.dark_mode_action.setIcon(QIcon("icons/moon.png"))
        else:
            set_light_mode(self.app)
            self.dark_mode_action.setIcon(QIcon("icons/sun.png"))

    def new_document(self):
        tab = BrailleTab(self, save_type="Texte + Braille")
        tab_count = self.tab_widget.count() + 1
        default_title = f"Document sans titre {tab_count}"
        self.tab_widget.addTab(tab, default_title)
        self.tab_widget.setCurrentWidget(tab)
        self.sync_text_areas(tab)
        self.update_counters()

    def close_tab(self, index):
        self.tab_widget.removeTab(index)

    def import_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Importer des fichiers", "",
            "Tous les fichiers (*.txt *.bfr *.pdf *.docx);;Fichiers texte (*.txt *.bfr);;Fichiers PDF (*.pdf);;Fichiers Word (*.docx)")
        for file_path in file_paths:
            text = self.file_handler.extract_text(file_path)
            if not text:
                text = "Fichier non pris en charge ou corrompu."
            filtered_text = ''.join(char for char in text if not ('\u2800' <= char <= '\u28FF'))
            save_type = "Texte uniquement" if not file_path.endswith(".bfr") else "Braille uniquement"
            tab = BrailleTab(self, file_path=file_path, save_type=save_type)
            tab.text_input.setPlainText(filtered_text)
            tab_title = os.path.basename(file_path) if file_path else "Document importé"
            self.tab_widget.addTab(tab, tab_title)
            self.sync_text_areas(tab)
            self.update_counters()
            if self.logged_in_user:
                fichier = Fichier(tab_title, file_path)
                self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
        if file_paths:
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)

    def import_image(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Importer une image", "",
            "Images (*.png *.jpg *.jpeg *.gif *.webp *.bmp *.tiff)")
        if not file_path:
            return

        try:
            braille_text = self.file_handler.image_to_braille(file_path, width=40, height=20, mode="contours")
            if not braille_text.strip():
                QMessageBox.warning(self, "Avertissement", "Aucun contenu braille généré à partir de l'image.")
                return
            tab = BrailleTab(self, file_path=file_path, save_type="Braille uniquement")
            tab.text_output.setPlainText(braille_text)
            tab.original_braille = braille_text
            tab_title = os.path.basename(file_path) if file_path else "Image importée"
            self.tab_widget.addTab(tab, tab_title)
            self.update_counters()
            self.tab_widget.setCurrentIndex(self.tab_widget.count() - 1)
            if self.logged_in_user:
                fichier = Fichier(tab_title, file_path)
                self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
        except Exception as e:
            QMessageBox.critical(self, "Erreur", f"Erreur lors de l'importation de l'image : {str(e)}")

    def save_document(self):
        tab = self.tab_widget.currentWidget()
        if not tab or (not tab.text_input.toPlainText().strip() and not tab.text_output.toPlainText().strip()):
            QMessageBox.warning(self, "Avertissement", "Aucun contenu à sauvegarder.")
            return

        if self.logged_in_user:
            titre = self.tab_widget.tabText(self.tab_widget.indexOf(tab)) or "Document sans titre"
            contenu = tab.text_input.toPlainText()
            texte = Texte(contenu, titre)
            self.db.ajouter_texte(self.logged_in_user.id, texte)

        if tab.file_path and os.path.exists(tab.file_path):
            if not os.access(tab.file_path, os.W_OK):
                QMessageBox.critical(self, "Erreur", f"Impossible d'écrire dans {tab.file_path}.")
                return
            try:
                if tab.file_path.endswith((".txt", ".bfr")):
                    content = tab.text_input.toPlainText() + "\n\n" + tab.text_output.toPlainText() if tab.save_type == "Texte + Braille" else \
                              tab.text_output.toPlainText() if tab.save_type == "Braille uniquement" else tab.text_input.toPlainText()
                    self.file_handler.save_text(tab.file_path, content)
                elif tab.file_path.endswith(".docx"):
                    self.file_handler.export_docx(tab.file_path, tab.text_input.document(), tab.text_output.toPlainText(), tab.save_type)
                elif tab.file_path.endswith(".pdf"):
                    self.file_handler.export_pdf(tab.file_path, tab.text_input.document(), tab.text_output.toPlainText(), tab.save_type)
                self.tab_widget.setTabText(self.tab_widget.indexOf(tab), os.path.basename(tab.file_path))
                QMessageBox.information(self, "Succès", f"Sauvegardé dans {tab.file_path}")
            except PermissionError:
                QMessageBox.critical(self, "Erreur", f"Permission refusée pour {tab.file_path}.")
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")
        else:
            self.save_document_as()

    def save_document_as(self):
        tab = self.tab_widget.currentWidget()
        if not tab or (not tab.text_input.toPlainText().strip() and not tab.text_output.toPlainText().strip()):
            QMessageBox.warning(self, "Avertissement", "Aucun contenu à sauvegarder.")
            return

        export_choice, ok = QInputDialog.getItem(self, "Options de sauvegarde", "Choisissez le contenu à sauvegarder :",
                                                ["Texte + Braille", "Braille uniquement", "Texte uniquement"], 0, False)
        if not ok:
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", "",
                                                   "Fichiers texte (*.txt);;Fichiers Braille (*.bfr);;Fichiers PDF (*.pdf);;Fichiers Word (*.docx)")
        if file_path:
            try:
                if file_path.endswith(".pdf"):
                    self.file_handler.export_pdf(file_path, tab.text_input.document(), tab.text_output.toPlainText(), export_choice)
                elif file_path.endswith(".docx"):
                    self.file_handler.export_docx(file_path, tab.text_input.document(), tab.text_output.toPlainText(), export_choice)
                elif file_path.endswith((".txt", ".bfr")):
                    content = tab.text_input.toPlainText() + "\n\n" + tab.text_output.toPlainText() if export_choice == "Texte + Braille" else \
                              tab.text_output.toPlainText() if export_choice == "Braille uniquement" else tab.text_input.toPlainText()
                    self.file_handler.save_text(file_path, content)
                tab.file_path = file_path
                tab.save_type = export_choice
                self.tab_widget.setTabText(self.tab_widget.indexOf(tab), os.path.basename(file_path))
                QMessageBox.information(self, "Succès", "Document sauvegardé.")
                if self.logged_in_user:
                    fichier = Fichier(os.path.basename(file_path), file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de la sauvegarde : {str(e)}")

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

    def export_to_pdf(self, file_path=None):
        tab = self.tab_widget.currentWidget()
        if not tab or (not tab.text_input.toPlainText().strip() and not tab.text_output.toPlainText().strip()):
            QMessageBox.warning(self, "Avertissement", "Aucun contenu à exporter.")
            return
        export_choice, ok = QInputDialog.getItem(self, "Options d'exportation", "Choisissez le contenu :",
                                                ["Texte + Braille", "Braille uniquement", "Texte uniquement"], 0, False)
        if not ok:
            return
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(self, "Exporter en PDF", "", "Fichiers PDF (*.pdf)")
        if file_path:
            try:
                self.file_handler.export_pdf(file_path, tab.text_input.document(), tab.text_output.toPlainText(), export_choice)
                tab.file_path = file_path
                tab.save_type = export_choice
                self.tab_widget.setTabText(self.tab_widget.indexOf(tab), os.path.basename(file_path))
                QMessageBox.information(self, "Succès", f"Fichier PDF exporté vers {file_path}")
                if self.logged_in_user:
                    fichier = Fichier(os.path.basename(file_path), file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'exportation : {str(e)}")

    def export_to_word(self, file_path=None):
        tab = self.tab_widget.currentWidget()
        if not tab or (not tab.text_input.toPlainText().strip() and not tab.text_output.toPlainText().strip()):
            QMessageBox.warning(self, "Avertissement", "Aucun contenu à exporter.")
            return
        export_choice, ok = QInputDialog.getItem(self, "Options d'exportation", "Choisissez le contenu :",
                                                ["Texte + Braille", "Braille uniquement", "Texte uniquement"], 0, False)
        if not ok:
            return
        if not file_path:
            file_path, _ = QFileDialog.getSaveFileName(self, "Exporter en Word", "", "Fichiers Word (*.docx)")
        if file_path:
            try:
                self.file_handler.export_docx(file_path, tab.text_input.document(), tab.text_output.toPlainText(), export_choice)
                tab.file_path = file_path
                tab.save_type = export_choice
                self.tab_widget.setTabText(self.tab_widget.indexOf(tab), os.path.basename(file_path))
                QMessageBox.information(self, "Succès", "Fichier Word exporté.")
                if self.logged_in_user:
                    fichier = Fichier(os.path.basename(file_path), file_path)
                    self.db.sauvegarder_fichier(self.logged_in_user.id, fichier)
            except Exception as e:
                QMessageBox.critical(self, "Erreur", f"Erreur lors de l'exportation : {str(e)}")

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

    def update_counters(self):
        tab = self.tab_widget.currentWidget()
        if tab:
            text = tab.text_input.toPlainText().strip()
            braille = tab.text_output.toPlainText().strip()
            lines = text.count('\n') + 1 if text else 0
            words = len(text.split()) if text else 0
            chars_per_page = 3000
            num_pages = max(1, len(text) // chars_per_page + 1)
            braille_lines = braille.count('\n') + 1 if braille else 0
            braille_pages = max(1, braille_lines // self.lines_per_page + 1)
            self.page_count.setText(f"Texte: {num_pages} | Braille: {braille_pages}")
            self.line_count.setText(str(lines))
            self.word_count.setText(str(words))
            braille_chars = len([c for c in braille if '\u2800' <= c <= '\u28FF']) if braille else 0
            self.status_bar.showMessage(f"Caractères Braille : {braille_chars}")
        else:
            self.page_count.setText("Texte: 0 | Braille: 0")
            self.line_count.setText("0")
            self.word_count.setText("0")
            self.status_bar.showMessage("Aucun onglet ouvert")

    def update_usage_time(self):
        if self.logged_in_user:
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
        if tab:
            tab.text_input.clear()
            tab.text_output.clear()
            tab.original_text = ""
            tab.original_braille = ""
            self.update_counters()

    def closeEvent(self, event):
        if self.logged_in_user:
            elapsed = self.usage_start_time.secsTo(QTime.currentTime())
            self.db.update_usage_time(self.logged_in_user.id, elapsed)
        self.db.fermer_connexion()
        event.accept()