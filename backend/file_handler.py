import os
import pdfplumber
from docx import Document
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from PyQt5.QtGui import QPainter, QFont
from PyQt5.QtPrintSupport import QPrinter
from PIL import Image, ImageEnhance
import pytesseract
import numpy as np
import cv2
import re
import tempfile
import unicodedata

class FileHandler:
    def __init__(self):
        self.last_gcode = None
        self.parent = None  # Référence à l'UI pour les interactions si nécessaire

    def extract_text(self, file_path, max_pages=10):
        """
        Extrait le texte d'un fichier (TXT, BFR, PDF, DOCX).
        :param file_path: Chemin du fichier.
        :param max_pages: Nombre maximum de pages à extraire pour les PDF.
        :return: Texte extrait ou chaîne vide en cas d'erreur.
        """
        try:
            if not os.path.exists(file_path):
                print(f"Erreur : Le fichier {file_path} n'existe pas.")
                return ""

            if file_path.lower().endswith('.txt') or file_path.lower().endswith('.bfr'):
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()

            elif file_path.lower().endswith('.pdf'):
                with pdfplumber.open(file_path) as pdf:
                    text = ''
                    for i, page in enumerate(pdf.pages):
                        if i >= max_pages:
                            break
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + '\n'
                    return text.strip()

            elif file_path.lower().endswith('.docx'):
                doc = Document(file_path)
                return '\n'.join(para.text for para in doc.paragraphs if para.text.strip())

            else:
                print(f"Format non pris en charge : {file_path}")
                return ""

        except Exception as e:
            print(f"Erreur lors de l'extraction de {file_path}: {str(e)}")
            return ""

    def _is_text_arabic(self, text):
        """
        Détermine si le texte contient principalement des caractères arabes (RTL).
        """
        arabic_chars = 0
        total_chars = 0
        for char in text:
            if unicodedata.bidirectional(char) in ('AL', 'R', 'BN'):
                arabic_chars += 1
            if char.isalpha():
                total_chars += 1
        return total_chars > 0 and (arabic_chars / total_chars) > 0.5

    def _text_to_braille_french(self, text):
        """
        Convertit un texte en Braille français (Grade 1).
        :param text: Texte à convertir.
        :return: Texte en Braille.
        """
        # Table de conversion Braille français (Grade 1)
        braille_table = {
            'a': '⠁', 'b': '⠃', 'c': '⠉', 'd': '⠙', 'e': '⠑', 'f': '⠋', 'g': '⠛', 'h': '⠓', 'i': '⠊',
            'j': '⠚', 'k': '⠅', 'l': '⠇', 'm': '⠍', 'n': '⠝', 'o': '⠕', 'p': '⠏', 'q': '⠟', 'r': '⠗',
            's': '⠎', 't': '⠞', 'u': '⠥', 'v': '⠧', 'w': '⠺', 'x': '⠭', 'y': '⠽', 'z': '⠵',
            'é': '⠿', 'è': '⠾', 'ê': '⠻', 'ë': '⠷', 'à': '⠈⠁', 'â': '⠈⠁', 'ô': '⠈⠕', 'î': '⠈⠊',
            'ù': '⠈⠥', 'ç': '⠯', 'œ': '⠪', '-': '⠤', '/': '⠌', ' ': ' ',
            '1': '⠼⠁', '2': '⠼⠃', '3': '⠼⠉', '4': '⠼⠙', '5': '⠼⠑',
            '6': '⠼⠋', '7': '⠼⠛', '8': '⠼⠓', '9': '⠼⠊', '0': '⠼⠕',
            '.': '⠲', ',': '⠂', ';': '⠆', ':': '⠒', '!': '⠖', '?': '⠦',
            '(': '⠦', ')': '⠴', '[': '⠦', ']': '⠴', '*': '⠔', '"': '⠦',
        }
        braille_text = ''
        for char in text.lower():
            braille_text += braille_table.get(char, ' ')  # Remplacer les caractères non mappés par un espace
        return braille_text

    def _text_to_braille_arabic(self, text):
        """
        Convertit un texte en Braille arabe (Grade 1).
        :param text: Texte à convertir.
        :return: Texte en Braille.
        """
        # Table de conversion Braille arabe (Grade 1) simplifiée
        braille_table = {
            'ا': '⠁', 'ب': '⠃', 'ت': '⠞', 'ث': '⠹', 'ج': '⠚', 'ح': '⠓', 'خ': '⠱', 'د': '⠙', 'ذ': '⠮',
            'ر': '⠗', 'ز': '⠵', 'س': '⠎', 'ش': '⠩', 'ص': '⠯', 'ض': '⠟', 'ط': '⠷', 'ظ': '⠧', 'ع': '⠫',
            'غ': '⠻', 'ف': '⠋', 'ق': '⠭', 'ك': '⠅', 'ل': '⠇', 'م': '⠍', 'ن': '⠝', 'ه': '⠗', 'و': '⠺',
            'ي': '⠽', 'ة': '⠢', ' ': ' ',
            '1': '⠼⠁', '2': '⠼⠃', '3': '⠼⠉', '4': '⠼⠙', '5': '⠼⠑',
            '6': '⠼⠋', '7': '⠼⠛', '8': '⠼⠓', '9': '⠼⠊', '0': '⠼⠕',
            '.': '⠲', ',': '⠂', ';': '⠆', ':': '⠒', '!': '⠖', '?': '⠦',
        }
        braille_text = ''
        # Inverser le texte arabe pour respecter l'ordre de lecture (de droite à gauche)
        text = text[::-1]
        for char in text:
            braille_text += braille_table.get(char, ' ')  # Remplacer les caractères non mappés par un espace
        return braille_text

    def convert_to_braille(self, text):
        """
        Convertit un texte en Braille, en fonction de la langue détectée.
        :param text: Texte à convertir.
        :return: Texte en Braille.
        """
        if not text.strip():
            return "⠁⠥⠉⠥⠝ ⠞⠑⠭⠞⠑ ⠁ ⠉⠕⠝⠧⠑⠗⠞⠊⠗⠲"

        is_arabic = self._is_text_arabic(text)
        if is_arabic:
            return self._text_to_braille_arabic(text)
        else:
            return self._text_to_braille_french(text)

    def image_to_braille(self, file_path, mode='text', width=40, height=20, contrast=2.0, lang='fra+ara', psm=6):
        """
        Convertit une image en texte et/ou Braille.
        :param file_path: Chemin de l'image.
        :param mode: 'text' (OCR), 'graphic' (formes), 'hybrid' (mixte).
        :param width: Largeur cible pour la conversion graphique.
        :param height: Hauteur cible pour la conversion graphique.
        :param contrast: Facteur de contraste pour l'image.
        :param lang: Langues pour l'OCR ('fra+ara' par défaut).
        :param psm: Mode de segmentation de page pour Tesseract (6 par défaut).
        :return: Tuple (texte extrait, texte Braille).
        """
        try:
            # Charger l'image
            with open(file_path, 'rb') as f:
                image_data = np.frombuffer(f.read(), np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError("Impossible de charger l'image. Le fichier est peut-être corrompu ou dans un format non supporté.")

            extracted_text = ""
            braille_text = ""

            # Ajuster le contraste pour l'OCR et le mode graphique
            image_pil = Image.fromarray(image)
            enhancer = ImageEnhance.Contrast(image_pil)
            image_pil = enhancer.enhance(contrast)
            image = np.array(image_pil)

            if mode in ['text', 'hybrid']:
                try:
                    # Prétraitement pour l'OCR
                    scale_factor = 3  # Augmenter la résolution pour une meilleure extraction
                    image_ocr = cv2.resize(image, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
                    image_ocr = cv2.GaussianBlur(image_ocr, (5, 5), 0)  # Réduire le bruit
                    _, image_ocr = cv2.threshold(image_ocr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    image_ocr_pil = Image.fromarray(image_ocr)

                    # Extraire le texte avec Tesseract
                    extracted_text = pytesseract.image_to_string(image_ocr_pil, lang=lang, config=f'--psm {psm} --oem 1')
                    print("Texte extrait par OCR :", extracted_text)

                    if extracted_text.strip():
                        # Nettoyer le texte extrait
                        extracted_text = extracted_text.replace('•', '-')
                        extracted_text = re.sub(r'\n+', '\n', extracted_text).strip()
                        extracted_text = re.sub(r'[!*]+', ' ', extracted_text)
                        extracted_text = extracted_text.replace('ä', 'a').replace('@', '').replace('>', '')
                        extracted_text = extracted_text.replace('0', 'o').replace('1', 'i')
                        # Convertir en Braille
                        braille_text = self.convert_to_braille(extracted_text)
                        if not braille_text.strip():
                            braille_text = "Erreur lors de la conversion du texte en Braille."
                        if mode == "text":
                            return extracted_text, braille_text
                    else:
                        print("Aucun texte extrait par l'OCR.")
                        extracted_text = "Aucun texte extrait."
                        braille_text = "⠁⠥⠉⠥⠝ ⠞⠑⠭⠞⠑ ⠑⠭⠞⠗⠁⠊⠞⠲"
                except Exception as e:
                    print(f"Erreur OCR : {e}")
                    extracted_text = "Erreur lors de l'extraction du texte."
                    braille_text = "⠑⠗⠗⠑⠥⠗ ⠇⠕⠗⠎ ⠙⠑ ⠇⠦⠑⠭⠞⠗⠁⠉⠞⠊⠕⠝ ⠙⠥ ⠞⠑⠭⠞⠑⠲"

            if mode in ['graphic', 'hybrid']:
                # Prétraitement pour le mode graphique
                image = cv2.bitwise_not(image)  # Inverser pour que les lignes sombres deviennent blanches
                image = cv2.GaussianBlur(image, (5, 5), 0)
                # Utiliser un seuillage adaptatif pour mieux capturer la courbe
                image = cv2.adaptiveThreshold(image, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                edges = cv2.Canny(image, 30, 100)  # Ajuster les seuils pour une détection fine
                kernel = np.ones((3, 3), np.uint8)
                edges = cv2.dilate(edges, kernel, iterations=2)  # Dilater pour une courbe plus continue
                image = cv2.resize(edges, (width * 2, height * 4), interpolation=cv2.INTER_NEAREST)

                braille_grid = []
                gcode_lines = ["G21", "G90", "M3 S1000"]
                has_content = False

                for y in range(0, height * 4, 4):
                    braille_row = []
                    for x in range(0, width * 2, 2):
                        block = image[y:y+4, x:x+2]
                        if block.shape != (4, 2):
                            braille_row.append(' ')
                            continue

                        # Calculer les points Braille pour un bloc 4x2
                        dots = 0
                        for i in range(4):
                            for j in range(2):
                                if block[i, j] > 128:  # Pixels blancs (contours) après inversion
                                    dot_position = (i * 2 + j)
                                    dots |= 1 << dot_position
                        braille_char = chr(0x2800 + dots)
                        braille_row.append(braille_char)

                        # Générer du G-code pour les zones non vides
                        if dots > 0:
                            has_content = True
                            gcode_x = x / 2.0
                            gcode_y = (height * 4 - y) / 4.0
                            gcode_lines.append(f"G01 X{gcode_x:.2f} Y{gcode_y:.2f} Z-0.1")

                    braille_grid.append(''.join(braille_row))

                gcode_lines.append("M5")
                self.last_gcode = "\n".join(gcode_lines) if has_content else None

                graphic_braille = '\n'.join(braille_grid).strip()
                if mode == "hybrid":
                    if braille_text and graphic_braille:
                        braille_text = braille_text + "\n\n--- Graphique ---\n" + graphic_braille
                    elif graphic_braille:
                        braille_text = "--- Graphique ---\n" + graphic_braille
                    elif braille_text:
                        braille_text = braille_text
                    else:
                        braille_text = "Erreur lors de la conversion en Braille."
                elif mode == "graphic":
                    braille_text = graphic_braille

            if braille_text:
                braille_lines = [line.rstrip() for line in braille_text.split('\n') if line.strip()]
                braille_text = '\n'.join(braille_lines)

            return extracted_text, braille_text if braille_text else "Erreur lors de la conversion en Braille."

        except Exception as e:
            print(f"Erreur lors de la conversion de l'image {file_path}: {str(e)}")
            return "Erreur lors de la conversion de l'image.", "⠑⠗⠗⠑⠥⠗ ⠇⠕⠗⠎ ⠙⠑ ⠇⠁ ⠉⠕⠝⠧⠑⠗⠎⠊⠕⠝ ⠙⠑ ⠇⠦⠊⠍⠁⠛⠑⠲"

    def save_text(self, file_path, content):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            raise Exception(f"Erreur lors de la sauvegarde de {file_path}: {str(e)}")

    def export_pdf(self, file_path, text_document, braille_text, save_type):
        try:
            doc = SimpleDocTemplate(file_path, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            if save_type in ['Texte + Braille', 'Texte uniquement']:
                text = text_document.toPlainText()
                if text.strip():
                    story.append(Paragraph("Texte:", styles['Heading1']))
                    story.append(Paragraph(text.replace('\n', '<br/>'), styles['BodyText']))
                    story.append(Spacer(1, 12))

            if save_type in ['Texte + Braille', 'Braille uniquement']:
                if braille_text.strip():
                    story.append(Paragraph("Braille:", styles['Heading1']))
                    story.append(Paragraph(braille_text.replace('\n', '<br/>'), styles['BodyText']))

            doc.build(story)
        except Exception as e:
            raise Exception(f"Erreur lors de l'exportation PDF {file_path}: {str(e)}")

    def export_docx(self, file_path, text_document, braille_text, save_type):
        try:
            doc = Document()

            if save_type in ['Texte + Braille', 'Texte uniquement']:
                text = text_document.toPlainText()
                if text.strip():
                    doc.add_heading("Texte", level=1)
                    doc.add_paragraph(text)

            if save_type in ['Texte + Braille', 'Braille uniquement']:
                if braille_text.strip():
                    doc.add_heading("Braille", level=1)
                    doc.add_paragraph(braille_text)

            doc.save(file_path)
        except Exception as e:
            raise Exception(f"Erreur lors de l'exportation DOCX {file_path}: {str(e)}")

    def export_to_gcode(self, file_path):
        try:
            if self.last_gcode is None:
                print("Aucun G-code disponible.")
                return False
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.last_gcode)
            return True
        except Exception as e:
            print(f"Erreur lors de l'exportation G-code {file_path}: {str(e)}")
            return False

    def print_content(self, printer, text, braille_text):
        try:
            painter = QPainter()
            if not painter.begin(printer):
                print("Erreur : Impossible d'initialiser l'impression.")
                return False

            font = QFont("Arial", 12)
            painter.setFont(font)

            y_position = 50
            margin = 50
            line_spacing = 20

            if text.strip():
                painter.drawText(margin, y_position, "Texte :")
                y_position += line_spacing
                for line in text.split('\n'):
                    painter.drawText(margin, y_position, line)
                    y_position += line_spacing
                    if y_position > printer.pageRect().height() - margin:
                        printer.newPage()
                        y_position = margin

            if braille_text.strip():
                y_position += line_spacing
                painter.drawText(margin, y_position, "Braille :")
                y_position += line_spacing
                for line in braille_text.split('\n'):
                    painter.drawText(margin, y_position, line)
                    y_position += line_spacing
                    if y_position > printer.pageRect().height() - margin:
                        printer.newPage()
                        y_position = margin

            painter.end()
            return True

        except Exception as e:
            print(f"Erreur lors de l'impression : {str(e)}")
            return False