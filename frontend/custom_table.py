from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QInputDialog, 
    QTableWidgetItem, QMessageBox
)
from PyQt5.QtCore import Qt
import os

class CustomBrailleTableWidget(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.init_ui()

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

        close_button = QPushButton("Fermer")  # Nouveau bouton
        close_button.clicked.connect(self.close_widget)  # Connecté à une nouvelle méthode
        button_layout.addWidget(close_button)

        layout.addLayout(button_layout)
        self.setLayout(layout)
        self.load_custom_table()

    def load_custom_table(self):
        if os.path.exists("custom_table.txt"):
            with open("custom_table.txt", "r", encoding="utf-8") as f:
                for line in f:
                    char, braille = line.strip().split(",")
                    row = self.table.rowCount()
                    self.table.insertRow(row)
                    self.table.setItem(row, 0, QTableWidgetItem(char))
                    self.table.setItem(row, 1, QTableWidgetItem(braille))

    def add_character(self):
        char, ok1 = QInputDialog.getText(self, "Nouveau caractère", "Entrez le caractère :")
        if ok1 and char:
            braille, ok2 = QInputDialog.getText(self, "Traduction Braille", "Entrez la traduction Braille :")
            if ok2 and braille:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(char))
                self.table.setItem(row, 1, QTableWidgetItem(braille))
                with open("custom_table.txt", "a", encoding="utf-8") as f:
                    f.write(f"{char},{braille}\n")
                self.parent.braille_engine.update_custom_table()
                QMessageBox.information(self, "Succès", "Caractère ajouté avec succès.")

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
                    self.table.setItem(row, 0, QTableWidgetItem(new_char))
                    self.table.setItem(row, 1, QTableWidgetItem(new_braille))
                    self.save_custom_table()
                    self.parent.braille_engine.update_custom_table()
                    QMessageBox.information(self, "Succès", "Caractère modifié avec succès.")

    def delete_character(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un caractère à supprimer.")
            return
        self.table.removeRow(row)
        self.save_custom_table()
        self.parent.braille_engine.update_custom_table()
        QMessageBox.information(self, "Succès", "Caractère supprimé avec succès.")

    def save_custom_table(self):
        with open("custom_table.txt", "w", encoding="utf-8") as f:
            for row in range(self.table.rowCount()):
                char = self.table.item(row, 0).text()
                braille = self.table.item(row, 1).text()
                f.write(f"{char},{braille}\n")

    def close_widget(self):  # Nouvelle méthode pour fermer le widget
        self.hide()  # Masque le widget
        self.parent.stack_layout.removeWidget(self)  # Retire le widget du layout
        self.deleteLater()  # Programme la suppression du widget pour libérer la mémoire