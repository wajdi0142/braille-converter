from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QInputDialog, 
    QTableWidgetItem, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer
import os

class CustomBrailleTableWidget(QDialog):
    def __init__(self, braille_engine, parent=None):
        super().__init__(parent)
        self.braille_engine = braille_engine
        self.parent = parent
        self.setWindowTitle("Personnaliser la table Braille")
        self.init_ui()
        # Flashing attributes
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._toggle_flash)
        self.flash_count = 0
        self.max_flash_count = 4  # Number of flash cycles (on/off)
        self.is_flashing = False
        self.default_border_color = "#D3D3D3"  # Light gray for default border
        self.focus_border_color = "#808080"  # Gray for focus
        self.table.setStyleSheet(f"border: 2px solid {self.default_border_color};")
        self._original_style = f"border: 2px solid {self.default_border_color};"

    def init_ui(self):
        layout = QVBoxLayout()
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Caractère", "Braille"])
        layout.addWidget(self.table)

        button_layout = QHBoxLayout()
        add_button = QPushButton("Ajouter caractère")
        add_button.clicked.connect(self.add_character)
        button_layout.addWidget(add_button)

        edit_button = QPushButton("Modifier caractère")
        edit_button.clicked.connect(self.edit_character)
        button_layout.addWidget(edit_button)

        delete_button = QPushButton("Supprimer caractère")
        delete_button.clicked.connect(self.delete_character)
        button_layout.addWidget(delete_button)

        close_button = QPushButton("Fermer")
        close_button.clicked.connect(self.accept)
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.load_custom_table()

    def load_custom_table(self):
        # Lire la table personnalisée chargée par BrailleEngine
        custom_mapping = self.braille_engine.custom_table
        
        # Effacer le contenu actuel de la table de l'interface avant de la remplir
        self.table.setRowCount(0)

        # Remplir la table de l'interface avec les données chargées
        # custom_mapping est un dictionnaire {caractère: braille}
        for char, braille in custom_mapping.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(char))
            self.table.setItem(row, 1, QTableWidgetItem(braille))

    def add_character(self):
        char, ok1 = QInputDialog.getText(self, "Nouveau caractère", "Entrez le caractère :")
        if ok1 and char:
            braille, ok2 = QInputDialog.getText(self, "Traduction Braille", "Entrez la traduction Braille :")
            if ok2 and braille:
                # Validation des caractères Braille
                if not all('\u2800' <= c <= '\u28FF' for c in braille):
                    QMessageBox.warning(self, "Erreur", "La traduction Braille contient des caractères invalides (doit être entre U+2800 et U+28FF).")
                    return
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(char))
                self.table.setItem(row, 1, QTableWidgetItem(braille))
                with open("custom_table.txt", "a", encoding="utf-8") as f:
                    f.write(f"{char},{braille}\n")
                self.braille_engine.update_custom_table()
                QMessageBox.information(self, "Succès", "Caractère ajouté avec succès.")
                self._start_flash()

    def edit_character(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un caractère à modifier.")
            return
        char_item = self.table.item(row, 0)
        braille_item = self.table.item(row, 1)
        if char_item and braille_item:
            new_char, ok1 = QInputDialog.getText(self, "Modifier caractère", "Nouveau caractère :", text=char_item.text())
            if ok1:
                new_braille, ok2 = QInputDialog.getText(self, "Modifier Braille", "Nouvelle traduction :", text=braille_item.text())
                if ok2:
                    # Validation des caractères Braille
                    if not all('\u2800' <= c <= '\u28FF' for c in new_braille):
                        QMessageBox.warning(self, "Erreur", "La traduction Braille contient des caractères invalides (doit être entre U+2800 et U+28FF).")
                        return
                    self.table.setItem(row, 0, QTableWidgetItem(new_char))
                    self.table.setItem(row, 1, QTableWidgetItem(new_braille))
                    self.save_custom_table()
                    self.braille_engine.update_custom_table()
                    QMessageBox.information(self, "Succès", "Caractère modifié avec succès.")
                    self._start_flash()

    def delete_character(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un caractère à supprimer.")
            return
        self.table.removeRow(row)
        self.save_custom_table()
        self.braille_engine.update_custom_table()
        QMessageBox.information(self, "Succès", "Caractère supprimé avec succès.")
        self._start_flash()

    def save_custom_table(self):
        with open("custom_table.txt", "w", encoding="utf-8") as f:
            for row in range(self.table.rowCount()):
                char = self.table.item(row, 0).text()
                braille = self.table.item(row, 1).text()
                f.write(f"{char},{braille}\n")

    def _start_flash(self):
        if not self.is_flashing:
            self.is_flashing = True
            self.flash_count = 0
            self._toggle_flash()
            self.flash_timer.start(200)  # Flash interval in milliseconds

    def _toggle_flash(self):
        if self.flash_count >= self.max_flash_count:
            self.flash_timer.stop()
            self.is_flashing = False
            self.table.setStyleSheet(self._original_style)
            return

        flash_color = "#0000FF"  # Blue for accessibility
        if self.flash_count % 2 == 0:
            self.table.setStyleSheet(f"border: 4px solid {flash_color};")
        else:
            self.table.setStyleSheet(f"border: 4px solid {self.focus_border_color};")

        self.flash_count += 1

    def close_widget(self):
        self.accept()