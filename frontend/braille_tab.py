# frontend/braille_tab.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLabel, QMessageBox, QPushButton
from PyQt5.QtCore import Qt, QTimer

class BrailleTab(QWidget):
    def __init__(self, parent, file_path=None, save_type="Texte + Braille"):
        super().__init__()
        self.parent = parent
        self.file_path = file_path
        self.save_type = save_type
        self.original_text = ""
        self.original_braille = ""
        self.is_updating = False
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        text_layout = QHBoxLayout()

        self.text_input_label = QLabel("Texte :")
        self.text_input = QTextEdit()
        self.text_input.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.text_input.setLineWrapColumnOrWidth(80)
        self.text_input.textChanged.connect(self.on_text_changed)
        self.text_input.setAccessibleName("Zone de texte")
        text_layout.addWidget(self.text_input_label)
        text_layout.addWidget(self.text_input)

        self.text_output_label = QLabel("Braille :")
        self.text_output = QTextEdit()
        self.text_output.setLineWrapMode(QTextEdit.FixedColumnWidth)
        self.text_output.setLineWrapColumnOrWidth(40)
        self.text_output.textChanged.connect(self.on_braille_changed)
        self.text_output.setAccessibleName("Zone de braille")
        text_layout.addWidget(self.text_output_label)
        text_layout.addWidget(self.text_output)

        self.lock_button = QPushButton("Verrouiller Braille")
        self.lock_button.clicked.connect(self.toggle_lock_braille)

        layout.addLayout(text_layout)
        layout.addWidget(self.lock_button)
        self.setLayout(layout)

    def on_text_changed(self):
        if self.is_updating:
            print("on_text_changed: is_updating is True, skipping")
            return
        print("on_text_changed: Text changed, calling update_conversion")
        self.is_updating = True
        try:
            self.text_input.setStyleSheet("border: 2px solid blue;")
            if self.parent:
                print("on_text_changed: Calling parent.update_conversion()")
                self.parent.update_conversion()
                self.validate_conversion()
            QTimer.singleShot(200, lambda: self.text_input.setStyleSheet(""))
        except Exception as e:
            print(f"on_text_changed: Error - {str(e)}")
        finally:
            self.is_updating = False
            print("on_text_changed: Finished")

    def on_braille_changed(self):
        if self.is_updating or self.text_output.isReadOnly():
            print("on_braille_changed: is_updating or readOnly, skipping")
            return
        print("on_braille_changed: Braille changed, calling update_conversion")
        self.is_updating = True
        try:
            self.text_output.setStyleSheet("border: 2px solid blue;")
            if self.parent:
                print("on_braille_changed: Calling parent.update_conversion()")
                self.parent.update_conversion()
                self.validate_conversion()
            QTimer.singleShot(200, lambda: self.text_output.setStyleSheet(""))
        except Exception as e:
            print(f"on_braille_changed: Error - {str(e)}")
        finally:
            self.is_updating = False
            print("on_braille_changed: Finished")

    def validate_conversion(self):
        text = self.text_input.toPlainText().strip()
        braille = self.text_output.toPlainText().strip()
        if not text or not braille:
            self.text_output.setStyleSheet("")
            return
        selected_table = self.parent.table_combo.currentText()
        reverse_text = self.parent.braille_engine.from_braille(braille, self.parent.available_tables[selected_table])
        if reverse_text.strip() != text.strip():
            self.text_output.setStyleSheet("border: 2px solid orange;")
        else:
            self.text_output.setStyleSheet("")

    def toggle_lock_braille(self):
        self.text_output.setReadOnly(not self.text_output.isReadOnly())
        self.lock_button.setText("Déverrouiller Braille" if self.text_output.isReadOnly() else "Verrouiller Braille")