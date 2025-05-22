from PyQt5.QtWidgets import QWidget, QHBoxLayout, QTextEdit, QScrollArea, QProgressDialog
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QTextOption
import logging

class ConversionWorker(QThread):
    """Thread de travail pour la conversion asynchrone."""
    conversion_done = pyqtSignal(str, str)
    progress_updated = pyqtSignal(int)

    def __init__(self, text, braille_engine, table, line_width, chunk_size=1000):
        super().__init__()
        self.text = text
        self.braille_engine = braille_engine
        self.table = table
        self.line_width = line_width
        self.chunk_size = chunk_size

    def run(self):
        try:
            total_chunks = (len(self.text) + self.chunk_size - 1) // self.chunk_size
            result_text = []
            result_braille = []

            for i in range(0, len(self.text), self.chunk_size):
                chunk = self.text[i:i + self.chunk_size]
                formatted_chunk = self.braille_engine.wrap_text_by_sentence(chunk, self.line_width)
                braille_chunk = self.braille_engine.to_braille(formatted_chunk, self.table, self.line_width)
                
                result_text.append(formatted_chunk)
                result_braille.append(braille_chunk)
                
                progress = int((i + len(chunk)) / len(self.text) * 100)
                self.progress_updated.emit(progress)

            self.conversion_done.emit('\n'.join(result_text), '\n'.join(result_braille))
        except Exception as e:
            logging.error(f"Erreur dans ConversionWorker: {str(e)}")
            self.conversion_done.emit("", "")

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
        self.pending_changes = []
        self.last_modified_lines = set()
        self._style_timer = QTimer()
        self._style_timer.setSingleShot(True)
        self._style_timer.timeout.connect(self.reset_borders)
        self._conversion_cache = {}  # Cache pour les conversions
        self._line_cache = {}  # Cache pour les lignes individuelles
        self._chunk_size = 1000  # Taille des morceaux pour le traitement
        self._max_cache_size = 1000  # Taille maximale du cache
        self.init_ui()

    @property
    def text_input(self):
        """Propriété pour accéder à la première page d'entrée."""
        return self.pages_input[0] if self.pages_input else None

    @property
    def text_output(self):
        """Propriété pour accéder à la première page de sortie."""
        return self.pages_output[0] if self.pages_output else None

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

    def load_large_file(self, file_path):
        """Charge un gros fichier de manière progressive."""
        try:
            progress = QProgressDialog("Chargement du fichier...", "Annuler", 0, 100, self)
            progress.setWindowModality(Qt.WindowModal)
            progress.show()

            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Diviser le contenu en morceaux
            chunks = [content[i:i + self._chunk_size] for i in range(0, len(content), self._chunk_size)]
            total_chunks = len(chunks)

            for i, chunk in enumerate(chunks):
                if progress.wasCanceled():
                    return

                # Mettre à jour la progression
                progress.setValue(int((i + 1) / total_chunks * 100))
                progress.setLabelText(f"Chargement du fichier... {i + 1}/{total_chunks} morceaux")

                # Ajouter le morceau au texte
                if i == 0:
                    self.text_input.setPlainText(chunk)
                else:
                    self.text_input.append(chunk)

                # Traiter le morceau
                self.process_chunk(chunk, i)

            progress.setValue(100)
            self.update_conversion()

        except Exception as e:
            logging.error(f"Erreur lors du chargement du fichier: {str(e)}")
            raise

    def process_chunk(self, chunk, chunk_index):
        """Traite un morceau de texte et met à jour le cache."""
        try:
            # Vérifier si le morceau est déjà dans le cache
            cache_key = f"{chunk}_{self.parent.table_combo.currentText()}_{self.parent.line_width}"
            if cache_key in self._conversion_cache:
                return self._conversion_cache[cache_key]

            # Convertir le morceau
            formatted_chunk = self.parent.braille_engine.wrap_text_by_sentence(chunk, self.parent.line_width)
            braille_chunk = self.parent.braille_engine.to_braille(
                formatted_chunk,
                self.parent.available_tables[self.parent.table_combo.currentText()],
                self.parent.line_width
            )

            # Gérer la taille du cache
            if len(self._conversion_cache) >= self._max_cache_size:
                # Supprimer les entrées les plus anciennes
                oldest_key = next(iter(self._conversion_cache))
                del self._conversion_cache[oldest_key]

            # Mettre en cache le résultat
            self._conversion_cache[cache_key] = (formatted_chunk, braille_chunk)
            return formatted_chunk, braille_chunk

        except Exception as e:
            logging.error(f"Erreur lors du traitement du morceau {chunk_index}: {str(e)}")
            return "", ""

    def process_line(self, line, line_index):
        """Traite une ligne individuelle avec mise en cache."""
        try:
            # Vérifier si la ligne est déjà dans le cache
            cache_key = f"{line}_{self.parent.table_combo.currentText()}_{self.parent.line_width}"
            if cache_key in self._line_cache:
                return self._line_cache[cache_key]

            # Convertir la ligne
            formatted_line = self.parent.braille_engine.wrap_text_by_sentence(line, self.parent.line_width)
            braille_line = self.parent.braille_engine.to_braille(
                formatted_line,
                self.parent.available_tables[self.parent.table_combo.currentText()],
                self.parent.line_width
            )

            # Gérer la taille du cache
            if len(self._line_cache) >= self._max_cache_size:
                oldest_key = next(iter(self._line_cache))
                del self._line_cache[oldest_key]

            # Mettre en cache le résultat
            self._line_cache[cache_key] = (formatted_line, braille_line)
            return formatted_line, braille_line

        except Exception as e:
            logging.error(f"Erreur lors du traitement de la ligne {line_index}: {str(e)}")
            return "", ""

    def on_text_changed(self):
        """Gère les changements de texte avec indicateurs visuels et planification de conversion."""
        if self.is_updating or self.parent.is_typing:
            return

        # Mettre à jour les styles visuels
        if not self._style_timer.isActive():
            for page_input in self.pages_input:
                page_input.setStyleSheet("QTextEdit { border: 2px solid blue; }")
            for page_output in self.pages_output:
                page_output.setStyleSheet("QTextEdit { border: 2px solid orange; }")
            self._style_timer.start(1000)

        # Planifier la conversion si nécessaire
        if not (self.is_imported and not self.parent.auto_update_enabled):
            if not self.parent.conversion_timer.isActive():
                self.parent.conversion_timer.start(50)

    def reset_borders(self):
        """Réinitialise les bordures des zones de texte à leur état par défaut."""
        if not self.is_updating:
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

    def connect_text_changed(self):
        """Connecte les signaux de changement de texte aux slots appropriés."""
        for page in self.pages_input + self.pages_output:
            page.textChanged.connect(self.parent.on_text_changed)

    def queue_manual_edit(self, cursor_pos, new_text):
        """Ajoute une modification manuelle à la file d'attente."""
        self.pending_changes.append((cursor_pos, new_text))

    def process_pending_changes(self):
        """Traite les modifications manuelles en attente pour la première page d'entrée."""
        if not self.pending_changes or not self.text_input:
            return
        self.is_updating = True
        cursor = self.text_input.textCursor()
        for cursor_pos, new_text in self.pending_changes:
            cursor.setPosition(cursor_pos)
            cursor.insertText(new_text)
        self.text_input.setTextCursor(cursor)
        self.pending_changes.clear()
        self.is_updating = False

    def update_conversion(self):
        """Met à jour la conversion avec gestion optimisée des modifications."""
        if self.is_updating:
            return

        self.is_updating = True
        try:
            text = self.get_all_text()
            if not text:
                return

            # Vérifier si le texte complet est dans le cache
            cache_key = f"{text}_{self.parent.table_combo.currentText()}_{self.parent.line_width}"
            if cache_key in self._conversion_cache:
                formatted_text, formatted_braille = self._conversion_cache[cache_key]
                self.text_output.setPlainText(formatted_braille)
                return

            # Traiter les modifications ligne par ligne
            old_lines = self.original_text.split('\n')
            new_lines = text.split('\n')
            modified_lines = set()

            # Identifier les lignes modifiées
            for i in range(min(len(old_lines), len(new_lines))):
                if old_lines[i] != new_lines[i]:
                    modified_lines.add(i)
            for i in range(len(old_lines), len(new_lines)):
                modified_lines.add(i)

            if len(modified_lines) < len(new_lines) * 0.3:  # Si moins de 30% des lignes sont modifiées
                # Traiter uniquement les lignes modifiées
                braille_lines = self.original_braille.split('\n') if self.original_braille else [''] * len(old_lines)
                for line_idx in modified_lines:
                    if line_idx < len(new_lines):
                        line = new_lines[line_idx]
                        if line.strip():
                            formatted_line, braille_line = self.process_line(line, line_idx)
                            while line_idx >= len(braille_lines):
                                braille_lines.append('')
                            braille_lines[line_idx] = braille_line
                        else:
                            while line_idx >= len(braille_lines):
                                braille_lines.append('')
                            braille_lines[line_idx] = ""

                # Ajuster la longueur des lignes
                if len(braille_lines) > len(new_lines):
                    braille_lines = braille_lines[:len(new_lines)]
                elif len(braille_lines) < len(new_lines):
                    braille_lines.extend([''] * (len(new_lines) - len(braille_lines)))

                formatted_braille = '\n'.join(braille_lines)
                self.text_output.setPlainText(formatted_braille)
                self.original_braille = formatted_braille
                self.original_text = text
            else:
                # Pour les modifications importantes, utiliser le worker
                if len(text) > self._chunk_size:
                    if self._conversion_thread and self._conversion_thread.isRunning():
                        return

                    progress = QProgressDialog("Conversion en cours...", "Annuler", 0, 100, self)
                    progress.setWindowModality(Qt.WindowModal)
                    progress.show()

                    self._conversion_thread = ConversionWorker(
                        text,
                        self.parent.braille_engine,
                        self.parent.available_tables[self.parent.table_combo.currentText()],
                        self.parent.line_width
                    )
                    self._conversion_thread.conversion_done.connect(
                        lambda t, b: self.on_conversion_complete(t, b, cache_key)
                    )
                    self._conversion_thread.progress_updated.connect(progress.setValue)
                    self._conversion_thread.start()
                else:
                    # Pour les petits fichiers, conversion directe
                    formatted_text = self.parent.braille_engine.wrap_text_by_sentence(text, self.parent.line_width)
                    formatted_braille = self.parent.braille_engine.to_braille(
                        formatted_text,
                        self.parent.available_tables[self.parent.table_combo.currentText()],
                        self.parent.line_width
                    )
                    self._conversion_cache[cache_key] = (formatted_text, formatted_braille)
                    self.text_output.setPlainText(formatted_braille)
                    self.original_text = formatted_text
                    self.original_braille = formatted_braille

        except Exception as e:
            logging.error(f"Erreur lors de la mise à jour de la conversion: {str(e)}")
        finally:
            self.is_updating = False

    def on_conversion_complete(self, formatted_text, formatted_braille, cache_key):
        """Gère la fin de la conversion asynchrone."""
        try:
            self._conversion_cache[cache_key] = (formatted_text, formatted_braille)
            self.text_output.setPlainText(formatted_braille)
            self.original_text = formatted_text
            self.original_braille = formatted_braille
        except Exception as e:
            logging.error(f"Erreur lors de la finalisation de la conversion: {str(e)}")