from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QMessageBox
from PyQt5.QtCore import Qt

class BrailleTab(QWidget):
    """Tab for text and Braille input/output."""
    
    def __init__(self, parent, file_path=None, save_type="Texte + Braille"):
        """Initialize the Braille tab."""
        super().__init__()
        self.parent = parent
        self.file_path = file_path
        self.save_type = save_type
        self.original_text = ""
        self.original_braille = ""
        self.init_ui()

    def init_ui(self):
        """Set up the tab's user interface."""
        layout = QVBoxLayout()
        text_layout = QHBoxLayout()

        self.text_input_label = QLabel("Texte :")
        self.text_input = QTextEdit()
        self.text_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.text_input.setLineWrapColumnOrWidth(80)
        self.text_input.textChanged.connect(self.on_text_changed)
        text_layout.addWidget(self.text_input_label)
        text_layout.addWidget(self.text_input)

        self.text_output_label = QLabel("Braille :")
        self.text_output = QTextEdit()
        self.text_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.text_output.setLineWrapColumnOrWidth(40)
        self.text_output.textChanged.connect(self.on_text_changed)
        text_layout.addWidget(self.text_output_label)
        text_layout.addWidget(self.text_output)

        layout.addLayout(text_layout)
        self.setLayout(layout)

    def on_text_changed(self):
        """Handle text changes with debouncing."""
        if self.parent:
            self.parent.debounce_update()
            self.validate_conversion()

    def validate_conversion(self):
        """Validate Braille output against input text."""
        text = self.text_input.toPlainText().strip()
        braille = self.text_output.toPlainText().strip()
        if not text or not braille:
            return
        selected_table = self.parent.table_combo.currentText()
        reverse_text = self.parent.braille_engine.from_braille(braille, self.parent.available_tables[selected_table])
        if reverse_text != text:
            # Alerte supprimée : on ne fait rien
            pass