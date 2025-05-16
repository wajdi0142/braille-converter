from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QScrollArea
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

class BrailleTab(QWidget):
    """Onglet pour l'édition de texte et braille avec support multi-pages et conversion asynchrone."""
    
    def __init__(self, parent, file_path=None, save_type="Texte + Braille"):
        """
        Initialise un onglet pour l'édition de texte et braille.
        
        Args:
            parent: Instance de BrailleUI (parent de l'onglet).
            file_path (str, optional): Chemin du fichier importé.
            save_type (str): Type de sauvegarde ('Texte + Braille', 'Texte', 'Braille').
        """
        super().__init__()
        self.parent = parent
        self.file_path = file_path
        self.save_type = save_type
        self.is_imported = file_path is not None
        self.is_updating = False
        self.original_text = ""
        self.original_braille = ""
        self.pages_input = []
        self.pages_output = []
        self._conversion_thread = None
        self.init_ui()

    def init_ui(self):
        """Initialise l'interface de l'onglet avec des zones de texte défilantes."""
        layout = QHBoxLayout(self)

        # Conteneur pour la zone de texte d'entrée
        self.input_container = QScrollArea()
        self.input_container.setWidgetResizable(True)
        self.input_widget = QWidget()
        self.input_layout = QHBoxLayout(self.input_widget)

        # Conteneur pour la zone de texte de sortie (braille)
        self.output_container = QScrollArea()
        self.output_container.setWidgetResizable(True)
        self.output_widget = QWidget()
        self.output_layout = QHBoxLayout(self.output_widget)

        # Ajout d'une page initiale
        self.add_page()

        # Configuration des conteneurs
        self.input_container.setWidget(self.input_widget)
        self.output_container.setWidget(self.output_widget)
        layout.addWidget(self.input_container)
        layout.addWidget(self.output_container)

        # Appliquer les styles de bordure par défaut
        self.reset_borders()

    def add_page(self):
        """Ajoute une nouvelle page avec des zones de texte pour le texte et le braille."""
        page_input = QTextEdit()
        page_input.setFont(QFont(self.parent.current_font, self.parent.base_font_size))
        page_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
        page_input.setLineWrapColumnOrWidth(self.parent.line_width)
        page_input.setAcceptRichText(True)
        page_input.textChanged.connect(self.on_text_changed)

        page_output = QTextEdit()
        page_output.setFont(QFont(self.parent.current_font, self.parent.base_font_size))
        page_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
        page_output.setLineWrapColumnOrWidth(self.parent.line_width)
        page_output.setAcceptRichText(True)
        page_output.textChanged.connect(self.on_text_changed)

        self.pages_input.append(page_input)
        self.pages_output.append(page_output)
        self.input_layout.addWidget(page_input)
        self.output_layout.addWidget(page_output)

    def on_text_changed(self):
        """
        Gère les changements de texte avec indicateurs visuels et planification de conversion.
        Déclenche une conversion après un délai si nécessaire.
        """
        if not self.is_updating and not self.parent.is_typing:
            for page_input in self.pages_input:
                page_input.setStyleSheet("QTextEdit { border: 2px solid blue; }")
            for page_output in self.pages_output:
                page_output.setStyleSheet("QTextEdit { border: 2px solid orange; }")
            QTimer.singleShot(1000, self.reset_borders)
            if not (self.is_imported and not self.parent.auto_update_enabled):
                # Planifier la conversion en utilisant le conversion_timer de BrailleUI
                if not self.parent.conversion_timer.isActive():
                    self.parent.conversion_timer.start(300)  # 300ms de délai pour éviter des appels trop fréquents

    def reset_borders(self):
        """Réinitialise les bordures des zones de texte à leur état par défaut."""
        for page_input in self.pages_input:
            page_input.setStyleSheet("QTextEdit { border: 1px solid gray; }")
        for page_output in self.pages_output:
            page_output.setStyleSheet("QTextEdit { border: 1px solid gray; }")

    def set_page_text(self, page_index, text):
        """
        Définit le texte d'une page spécifique.
        
        Args:
            page_index (int): Index de la page.
            text (str): Texte à définir.
        """
        while page_index >= len(self.pages_input):
            self.add_page()
        self.is_updating = True
        self.pages_input[page_index].setPlainText(text)
        self.original_text = self.get_all_text()
        self.is_updating = False

    def set_page_braille(self, page_index, braille):
        """
        Définit le braille d'une page spécifique.
        
        Args:
            page_index (int): Index de la page.
            braille (str): Braille à définir.
        """
        while page_index >= len(self.pages_output):
            self.add_page()
        self.is_updating = True
        self.pages_output[page_index].setPlainText(braille)
        self.original_braille = self.get_all_braille()
        self.is_updating = False

    def get_all_text(self):
        """Récupère tout le texte des pages d'entrée."""
        return "\n".join(page.toPlainText() for page in self.pages_input)

    def get_all_braille(self):
        """Récupère tout le braille des pages de sortie."""
        return "\n".join(page.toPlainText() for page in self.pages_output)

    def update_font_and_width(self):
        """Met à jour la police et la largeur de ligne pour toutes les pages."""
        scale = self.parent.zoom_slider.value() / 100.0
        font_size = int(self.parent.base_font_size * scale)
        font = QFont(self.parent.current_font, font_size)
        for page_input, page_output in zip(self.pages_input, self.pages_output):
            page_input.setFont(font)
            page_output.setFont(font)
            page_input.setLineWrapColumnOrWidth(self.parent.line_width)
            page_output.setLineWrapColumnOrWidth(self.parent.line_width)