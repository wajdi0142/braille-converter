from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QPushButton, QInputDialog, 
    QTableWidgetItem, QMessageBox, QLabel, QComboBox, QRadioButton, QButtonGroup, QWidget
)
from PyQt5.QtCore import Qt, QTimer
import os

class CustomBrailleTableWidget(QDialog):
    def __init__(self, braille_engine, parent=None):
        super().__init__(parent)
        self.braille_engine = braille_engine
        self.parent = parent
        self.setWindowTitle("Personnaliser la table Braille")
        
        # Initialize attributes for language and grade
        self.available_tables = self.braille_engine.get_available_tables()
        self.languages = sorted(list(set([name.split(' ')[0] for name in self.available_tables.keys()])))
        self.current_language = self.languages[0] if self.languages else ""
        self.grades = ["Grade 1", "Grade 2"]
        self.current_grade = self.grades[0]
        self.current_table_name = self._get_current_table_name()
        
        # Initialize flashing attributes, but move styling variables to init_ui
        self.flash_timer = QTimer(self)
        self.flash_timer.timeout.connect(self._toggle_flash)
        self.flash_count = 0
        self.max_flash_count = 4  # Number of flash cycles (on/off)
        self.is_flashing = False
        # self.default_border_color = "#D3D3D3"  # Move to init_ui
        # self.focus_border_color = "#808080"  # Move to init_ui
        # self.table.setStyleSheet(f"border: 2px solid {self.default_border_color};") # Move to init_ui
        # self._original_style = f"border: 2px solid {self.default_border_color};" # Move to init_ui

        self.init_ui()

        # Load the initial custom table based on default selection
        # self.load_custom_table() # Moved to init_ui
        # self._update_title() # Moved to init_ui

    def init_ui(self):
        layout = QVBoxLayout()

        # Title Label
        self.title_label = QLabel("Table de conversion") # Initial title, will be updated
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-size: 16pt; font-weight: bold;")
        layout.addWidget(self.title_label)

        # Language and Grade Selection
        selection_layout = QHBoxLayout()

        # Language Dropdown
        language_label = QLabel("Langue:")
        selection_layout.addWidget(language_label)
        self.language_combo = QComboBox()
        self.language_combo.addItems(self.languages)
        self.language_combo.currentTextChanged.connect(self._on_language_changed)
        selection_layout.addWidget(self.language_combo)

        selection_layout.addStretch()

        # Grade Radio Buttons
        grade_label = QLabel("Grade:")
        selection_layout.addWidget(grade_label)
        self.grade_group = QButtonGroup(self)
        self.grade1_radio = QRadioButton("Grade 1")
        self.grade2_radio = QRadioButton("Grade 2")

        self.grade1_radio.toggled.connect(lambda: self._on_grade_changed("Grade 1"))
        self.grade2_radio.toggled.connect(lambda: self._on_grade_changed("Grade 2"))

        self.grade_group.addButton(self.grade1_radio)
        self.grade_group.addButton(self.grade2_radio)

        selection_layout.addWidget(self.grade1_radio)
        selection_layout.addWidget(self.grade2_radio)

        # Set initial grade selection
        if self.current_grade == "Grade 1":
            self.grade1_radio.setChecked(True)
        else:
            self.grade2_radio.setChecked(True)

        layout.addLayout(selection_layout)

        # Table Widget
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Caractère", "Braille"])
        layout.addWidget(self.table)
        
        # Initialize table styling variables and apply style here after self.table is created
        self.default_border_color = "#D3D3D3"  # Light gray for default border
        self.focus_border_color = "#808080"  # Gray for focus
        self.table.setStyleSheet(f"border: 2px solid {self.default_border_color};")
        self._original_style = f"border: 2px solid {self.default_border_color};"

        # Button Layout (Existing)
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
        # self.load_custom_table() # Moved loading to __init__
        
        # Load the initial custom table and update title after UI is initialized
        self.load_custom_table()
        self._update_title()

    def _get_current_table_name(self):
        """ Determines the full table name (e.g., 'Français (grade 2)') based on current language and grade. """
        print(f"_get_current_table_name: current_language={self.current_language}, current_grade={self.current_grade}")
        print(f"_get_current_table_name: available_tables.keys()={self.available_tables.keys()}")
        for name in self.available_tables.keys():
            # Modify matching logic to be more flexible
            if self.current_language.lower() in name.lower() and self.current_grade.lower().replace(' ', '') in name.lower().replace(' ', ''):
                 print(f"_get_current_table_name: Matched table name: {name}")
                 return name
        print("_get_current_table_name: No table name matched.")
        return None

    def _update_title(self):
        """ Updates the window title and the label above the table. """
        if self.current_table_name:
            title_text = f"Table de conversion – {self.current_language} – {self.current_grade}"
            self.setWindowTitle(f"Personnaliser la table Braille - {self.current_language} ({self.current_grade})")
            self.title_label.setText(title_text)
        else:
            self.setWindowTitle("Personnaliser la table Braille")
            self.title_label.setText("Table de conversion")

    def _on_language_changed(self, language):
        """ Handles language dropdown selection change. """
        self.current_language = language
        self.current_table_name = self._get_current_table_name()
        # Only load table if a valid table name is found
        if self.current_table_name:
            self.load_custom_table()
        else:
            # If no valid table found, clear the table view
            self.table.setRowCount(0)
            QMessageBox.warning(self, "Avertissement", f"Aucune table trouvée pour la langue sélectionnée : {language}")
        self._update_title()

    def _on_grade_changed(self, grade):
        """ Handles grade radio button selection change. """
        # Ensure this is only triggered by actual selection, not initialization
        # Add check for self.table before accessing it
        if not hasattr(self, 'table') or self.table is None:
            return
            
        if self.grade_group.checkedButton() is None:
             return # Avoid triggering on initialization before a button is checked
             
        if self.grade1_radio.isChecked() and grade == "Grade 1":
             self.current_grade = grade
             self.current_table_name = self._get_current_table_name()
             # Only load table if a valid table name is found
             if self.current_table_name:
                 self.load_custom_table()
             else:
                 # If no valid table found, clear the table view
                 self.table.setRowCount(0)
                 QMessageBox.warning(self, "Avertissement", f"Aucune table trouvée pour le grade sélectionné : {grade}")
             self._update_title()
        elif self.grade2_radio.isChecked() and grade == "Grade 2":
             self.current_grade = grade
             self.current_table_name = self._get_current_table_name()
             # Only load table if a valid table name is found
             if self.current_table_name:
                 self.load_custom_table()
             else:
                 # If no valid table found, clear the table view
                 self.table.setRowCount(0)
                 QMessageBox.warning(self, "Avertissement", f"Aucune table trouvée pour le grade sélectionné : {grade}")
             self._update_title()


    def load_custom_table(self):
        """ Loads the custom table for the currently selected language and grade. """
        # Add a check to ensure self.table is initialized
        if not hasattr(self, 'table') or self.table is None:
            return # Exit if table is not ready
            
        self.table.setRowCount(0)
        if self.current_table_name and self.current_table_name in self.braille_engine.all_custom_tables:
            custom_mapping = self.braille_engine.all_custom_tables[self.current_table_name]
            for char, braille in custom_mapping.items():
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(char))
                self.table.setItem(row, 1, QTableWidgetItem(braille))
        # If no custom table exists for the selection, the table will remain empty, which is correct.

    def add_character(self):
        char, ok1 = QInputDialog.getText(self, "Nouveau caractère", "Entrez le caractère :")
        if ok1 and char:
            braille, ok2 = QInputDialog.getText(self, "Traduction Braille", "Entrez la traduction Braille :")
            if ok2 and braille:
                if not all('\u2800' <= c <= '\u28FF' for c in braille):
                    QMessageBox.warning(self, "Erreur", "La traduction Braille contient des caractères invalides (doit être entre U+2800 et U+28FF).")
                    return
                    
                # Add to the current custom table in BrailleEngine
                if self.current_table_name:
                    if self.current_table_name not in self.braille_engine.all_custom_tables:
                        self.braille_engine.all_custom_tables[self.current_table_name] = {}
                    self.braille_engine.all_custom_tables[self.current_table_name][char] = braille
                    self.braille_engine.save_custom_tables() # Save all custom tables
                    self.load_custom_table() # Reload the table to show the added character
                    QMessageBox.information(self, "Succès", "Caractère ajouté avec succès.")
                    self._start_flash()
                else:
                     QMessageBox.warning(self, "Erreur", "Impossible d'ajouter le caractère: sélection de table invalide.")

    def edit_character(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un caractère à modifier.")
            return
        char_item = self.table.item(row, 0)
        braille_item = self.table.item(row, 1)
        if char_item and braille_item and self.current_table_name:
            original_char = char_item.text()
            original_braille = braille_item.text()
            
            new_char, ok1 = QInputDialog.getText(self, "Modifier caractère", "Nouveau caractère :", text=original_char)
            if ok1:
                new_braille, ok2 = QInputDialog.getText(self, "Modifier Braille", "Nouvelle traduction :", text=original_braille)
                if ok2:
                    if not all('\u2800' <= c <= '\u28FF' for c in new_braille):
                        QMessageBox.warning(self, "Erreur", "La traduction Braille contient des caractères invalides (doit être entre U+2800 et U+28FF).")
                        return
                        
                    # Update in the current custom table in BrailleEngine
                    if self.current_table_name in self.braille_engine.all_custom_tables:
                        # Remove the old entry if the character changed
                        if new_char != original_char and original_char in self.braille_engine.all_custom_tables[self.current_table_name]:
                             del self.braille_engine.all_custom_tables[self.current_table_name][original_char]
                        # Add or update the new entry
                        self.braille_engine.all_custom_tables[self.current_table_name][new_char] = new_braille
                        self.braille_engine.save_custom_tables() # Save all custom tables
                        self.load_custom_table() # Reload the table
                        QMessageBox.information(self, "Succès", "Caractère modifié avec succès.")
                        self._start_flash()
                    else:
                        QMessageBox.warning(self, "Erreur", "Impossible de modifier le caractère: sélection de table invalide.")


    def delete_character(self):
        row = self.table.currentRow()
        if row == -1:
            QMessageBox.warning(self, "Erreur", "Sélectionnez un caractère à supprimer.")
            return
            
        char_item = self.table.item(row, 0)
        if char_item and self.current_table_name and self.current_table_name in self.braille_engine.all_custom_tables:
            char_to_delete = char_item.text()
            if char_to_delete in self.braille_engine.all_custom_tables[self.current_table_name]:
                del self.braille_engine.all_custom_tables[self.current_table_name][char_to_delete]
                self.braille_engine.save_custom_tables() # Save all custom tables
                self.table.removeRow(row) # Remove from the GUI table
                QMessageBox.information(self, "Succès", "Caractère supprimé avec succès.")
                self._start_flash()
            else:
                 QMessageBox.warning(self, "Erreur", "Caractère non trouvé dans la table personnalisée actuelle.")
        else:
             QMessageBox.warning(self, "Erreur", "Impossible de supprimer le caractère: sélection de table invalide.")

    def save_custom_table(self):
        # This method is no longer needed as changes are saved directly via braille_engine.save_custom_tables()
        pass

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