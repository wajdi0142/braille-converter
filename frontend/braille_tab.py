from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QScrollArea, QPushButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QTextCursor

class BrailleTab(QWidget):
    def __init__(self, parent, file_path=None, save_type="Texte + Braille"):
        super().__init__()
        self.parent = parent
        self.file_path = file_path
        self.save_type = save_type
        self.pages_input = []
        self.pages_output = []
        self.original_text = ""
        self.original_braille = ""
        self.init_ui()

    def init_ui(self):
        # Mise en page principale
        layout = QHBoxLayout(self)

        # Conteneur pour la zone de texte d'entrée
        self.input_container = QScrollArea()
        self.input_container.setWidgetResizable(True)
        self.input_widget = QWidget()
        self.input_layout = QHBoxLayout(self.input_widget)

        # Conteneur pour la zone de texte de sortie (Braille)
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

    def add_page(self):
        # Créer une nouvelle zone de texte pour l'entrée
        page_input = QTextEdit()
        page_input.setFont(QFont(self.parent.current_font, self.parent.base_font_size))
        page_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
        page_input.setLineWrapColumnOrWidth(self.parent.line_width)
        page_input.setAcceptRichText(True)
        page_input.textChanged.connect(self.parent.update_conversion)

        # Créer une nouvelle zone de texte pour la sortie (Braille)
        page_output = QTextEdit()
        page_output.setFont(QFont(self.parent.current_font, self.parent.base_font_size))
        page_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
        page_output.setLineWrapColumnOrWidth(self.parent.line_width)
        page_output.setAcceptRichText(True)
        page_output.textChanged.connect(self.parent.update_conversion)

        # Ajouter les pages aux listes
        self.pages_input.append(page_input)
        self.pages_output.append(page_output)

        # Ajouter les widgets au layout
        self.input_layout.addWidget(page_input)
        self.output_layout.addWidget(page_output)

    def set_page_text(self, page_index, text):
        while page_index >= len(self.pages_input):
            self.add_page()
        self.pages_input[page_index].setPlainText(text)
        self.original_text = self.get_all_text()

    def set_page_braille(self, page_index, braille):
        while page_index >= len(self.pages_output):
            self.add_page()
        self.pages_output[page_index].setPlainText(braille)
        self.original_braille = self.get_all_braille()

    def get_all_text(self):
        return "\n".join(page.toPlainText() for page in self.pages_input)

    def get_all_braille(self):
        return "\n".join(page.toPlainText() for page in self.pages_output)

    def reset_borders(self):
        for page_input in self.pages_input:
            page_input.setStyleSheet("")
        for page_output in self.pages_output:
            page_output.setStyleSheet("")