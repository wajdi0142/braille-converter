import os
import pdfplumber
from docx import Document
from reportlab.lib.units import mm
from PyQt5.QtGui import QPainter, QFont
from PyQt5.QtPrintSupport import QPrinter
from PIL import Image, ImageEnhance
import pytesseract
import numpy as np
import cv2
import re
import unicodedata
import logging

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from xml.sax.saxutils import escape

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration des polices
BRAILLE_FONT_NAME = "Noto Sans Braille"
FALLBACK_FONT = "Times New Roman"
FONT_PATH = os.getenv("FONT_PATH", r"C:\Users\LENOVO\Downloads\Noto_Sans_Symbols_2\NotoSansSymbols2-Regular.ttf")

# Constants for export_pdf
TEXT_FONT_NAME = "Times New Roman"
FONT_PATHS = {
    "Times New Roman": "C:/Windows/Fonts/times.ttf",
    "Times New Roman-Bold": "C:/Windows/Fonts/timesbd.ttf",
    "Times New Roman-Italic": "C:/Windows/Fonts/timesi.ttf",
    "Noto Sans Braille": FONT_PATH,
}
DEFAULT_LINES_PER_PAGE = 25
DEFAULT_LINE_WIDTH = 120
DEFAULT_INDENT = 0
DEFAULT_LINE_SPACING = 1.0

class FileHandler:
    def __init__(self):
        self.last_gcode = None
        self.parent = None

    def extract_text(self, file_path, max_pages=10):
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
        arabic_chars = 0
        total_chars = 0
        for char in text:
            if unicodedata.bidirectional(char) in ('AL', 'R', 'BN'):
                arabic_chars += 1
            if char.isalpha():
                total_chars += 1
        return total_chars > 0 and (arabic_chars / total_chars) > 0.5

    def _text_to_braille_french(self, text):
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
            braille_text += braille_table.get(char, ' ')
        return braille_text

    def _text_to_braille_arabic(self, text):
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
        text = text[::-1]
        for char in text:
            braille_text += braille_table.get(char, ' ')
        return braille_text

    def convert_to_braille(self, text):
        if not text.strip():
            return "⠁⠥⠉⠥⠝ ⠞⠑⠭⠞⠑ ⠁ ⠉⠕⠝⠧⠑⠗⠞⠊⠗⠲"

        is_arabic = self._is_text_arabic(text)
        if is_arabic:
            return self._text_to_braille_arabic(text)
        else:
            return self._text_to_braille_french(text)

    def image_to_braille(self, file_path, mode='text', width=40, height=20, contrast=2.0, lang='fra+ara', psm=6):
        try:
            with open(file_path, 'rb') as f:
                image_data = np.frombuffer(f.read(), np.uint8)
            image = cv2.imdecode(image_data, cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError("Impossible de charger l'image.")

            extracted_text = ""
            braille_text = ""
            graphic_braille = ""

            image_pil = Image.fromarray(image)
            enhancer = ImageEnhance.Contrast(image_pil)
            image_pil = enhancer.enhance(contrast)
            image = np.array(image_pil)

            if mode in ['text', 'hybrid']:
                try:
                    scale_factor = 3
                    image_ocr = cv2.resize(image, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
                    image_ocr = cv2.GaussianBlur(image_ocr, (5, 5), 0)
                    _, image_ocr = cv2.threshold(image_ocr, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    image_ocr_pil = Image.fromarray(image_ocr)

                    extracted_text = pytesseract.image_to_string(image_ocr_pil, lang=lang, config=f'--psm {psm} --oem 1')
                    print("Texte extrait par OCR :", extracted_text)

                    if extracted_text.strip():
                        extracted_text = extracted_text.replace('•', '- COOKIES')
                        extracted_text = re.sub(r'\n+', '\n', extracted_text).strip()
                        extracted_text = re.sub(r'[!*]+', ' ', extracted_text)
                        extracted_text = extracted_text.replace('ä', 'a').replace('@', '').replace('>', '')
                        extracted_text = extracted_text.replace('0', 'o').replace('1', 'i')
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
                    braille_text = "⠑⠗⠗⠑⠥⠗ ⠇⠕⠗⠎ ⠙⠑ ⠇⠦⠑⠭⠞⠗⠁⠉⠞⠊⠕⠝⠲"

            if mode in ['graphic', 'hybrid']:
                image_graphic = cv2.resize(image, (width * 2, height * 4), interpolation=cv2.INTER_AREA)
                _, image_graphic = cv2.threshold(image_graphic, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                graphic_braille = self._image_to_braille_graphic(image_graphic, width, height)
                self.last_gcode = graphic_braille

                if mode == 'graphic':
                    return extracted_text, graphic_braille
                else:
                    combined_braille = f"{braille_text}\n\n=== Représentation graphique ===\n{graphic_braille}"
                    return extracted_text, combined_braille

            return extracted_text, braille_text

        except Exception as e:
            print(f"Erreur lors de la conversion de l'image : {e}")
            return "Erreur lors de la conversion.", "⠑⠗⠗⠑⠥⠗ ⠙⠑ ⠉⠕⠝⠧⠑⠗⠎⠊⠕⠝⠲"

    def _image_to_braille_graphic(self, image, width, height):
        braille_chars = ['⠀', '⠁', '⠂', '⠃', '⠄', '⠅', '⠆', '⠇', '⠈', '⠉', '⠊', '⠋', '⠌', '⠍', '⠎', '⠏',
                         '⠐', '⠑', '⠒', '⠓', '⠔', '⠕', '⠖', '⠗', '⠘', '⠙', '⠚', '⠛', '⠜', '⠝', '⠞', '⠟',
                         '⠠', '⠡', '⠢', '⠣', '⠤', '⠥', '⠦', '⠧', '⠨', '⠩', '⠪', '⠫', '⠬', '⠭', '⠮', '⠯',
                         '⠰', '⠱', '⠲', '⠳', '⠴', '⠵', '⠶', '⠷', '⠸', '⠹', '⠺', '⠻', '⠼', '⠽', '⠾', '⠿']

        result = []
        for y in range(0, height * 4, 4):
            row = ''
            for x in range(0, width * 2, 2):
                pixels = []
                for dy in range(4):
                    for dx in range(2):
                        pixel_y = y + dy
                        pixel_x = x + dx
                        if pixel_y < image.shape[0] and pixel_x < image.shape[1]:
                            pixel = image[pixel_y, pixel_x]
                            pixels.append(1 if pixel < 128 else 0)
                        else:
                            pixels.append(0)
                index = (
                    pixels[0] * 1 + pixels[1] * 2 + pixels[2] * 4 + pixels[3] * 8 +
                    pixels[4] * 16 + pixels[5] * 32 + pixels[6] * 64 + pixels[7] * 128
                )
                index = min(index, len(braille_chars) - 1)
                row += braille_chars[index]
            result.append(row)
        return '\n'.join(result)

    def save_text(self, file_path, content):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception as e:
            raise Exception(f"Erreur lors de la sauvegarde : {str(e)}")

    def export_pdf(self, file_path, text_document, braille_text, save_type, font_name=BRAILLE_FONT_NAME, author=None, doc_name="Document"):
        """
        Export a text and/or Braille document to PDF.
        
        Args:
            file_path (str): Path to save the PDF.
            text_document: QTextDocument containing the text content.
            braille_text (str): Braille content as a string.
            save_type (str): Export type ("Texte + Braille", "Texte uniquement", "Braille uniquement").
            font_name (str): Braille font name (default: Noto Sans Braille).
            author (str): Document author (optional).
            doc_name (str): Document title (default: "Document").
        
        Raises:
            ValueError: If inputs are invalid.
            Exception: If PDF generation fails.
        """
        try:
            # Input validation
            if not file_path or not isinstance(file_path, str):
                raise ValueError("Invalid file path")
            if not text_document and save_type in ["Texte + Braille", "Texte uniquement"]:
                raise ValueError("Text document required for selected save type")
            if not braille_text and save_type in ["Texte + Braille", "Braille uniquement"]:
                raise ValueError("Braille text required for selected save type")
            if save_type not in ["Texte + Braille", "Texte uniquement", "Braille uniquement"]:
                raise ValueError("Invalid save type")

            # Step 1: Font handling
            text_font = TEXT_FONT_NAME
            braille_font = font_name

            # Register text font and its variants
            font_variants = {
                "Times New Roman": "Times New Roman",
                "Times New Roman-Bold": "Times New Roman-Bold",
                "Times New Roman-Italic": "Times New Roman-Italic",
            }
            for font_name, font_key in font_variants.items():
                if font_key not in pdfmetrics.getRegisteredFontNames():
                    font_path = FONT_PATHS.get(font_key)
                    if font_path and os.path.exists(font_path):
                        try:
                            pdfmetrics.registerFont(TTFont(font_key, font_path))
                            logging.debug(f"Font '{font_key}' registered successfully from {font_path}")
                        except Exception as e:
                            logging.warning(f"Error registering font '{font_key}': {str(e)}")
                    else:
                        logging.warning(f"Font file not found for '{font_key}' at {font_path}")

            # Fallback if Times New Roman fails
            if text_font not in pdfmetrics.getRegisteredFontNames():
                logging.warning(f"Text font '{text_font}' not registered, falling back to '{FALLBACK_FONT}'")
                text_font = FALLBACK_FONT
            if braille_font not in pdfmetrics.getRegisteredFontNames():
                font_path = FONT_PATHS.get(braille_font)
                if font_path and os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(braille_font, font_path))
                        logging.debug(f"Font '{braille_font}' registered successfully from {font_path}")
                    except Exception as e:
                        logging.error(f"Error registering font '{braille_font}': {str(e)}")
                        braille_font = FALLBACK_FONT

            # Step 2: Configure PDF document with improved margins
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                leftMargin=15 * mm,  # Marges plus confortables
                rightMargin=15 * mm,
                topMargin=20 * mm,
                bottomMargin=20 * mm,
                author=author if author else "Utilisateur non connecté",
                title=doc_name,
                subject="Conversion Texte/Braille",
                creator="Convertisseur Texte ↔ Braille"
            )

            # Step 3: Define improved styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                name="Title",
                fontName=text_font,
                fontSize=16,  # Taille de police plus grande pour le titre
                spaceAfter=20,  # Plus d'espace après le titre
                spaceBefore=10,  # Espace avant le titre
                alignment=TA_CENTER,
                textColor='#000000'  # Couleur noire pour le titre
            )
            text_style = ParagraphStyle(
                name="Text",
                fontName=text_font,
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,  # Plus d'espace entre les paragraphes
                leading=14,  # Meilleur espacement des lignes
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'  # Gris foncé pour le texte
            )
            text_style_bold = ParagraphStyle(
                name="TextBold",
                fontName=f"{text_font}-Bold",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'  # Noir pour le texte en gras
            )
            text_style_italic = ParagraphStyle(
                name="TextItalic",
                fontName=f"{text_font}-Italic",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_underline = ParagraphStyle(
                name="TextUnderline",
                fontName=text_font,
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_bold_italic = ParagraphStyle(
                name="TextBoldItalic",
                fontName=f"{text_font}-BoldItalic" if f"{text_font}-BoldItalic" in pdfmetrics.getRegisteredFontNames() else f"{text_font}-Italic",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            text_style_bold_underline = ParagraphStyle(
                name="TextBoldUnderline",
                fontName=f"{text_font}-Bold",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            text_style_italic_underline = ParagraphStyle(
                name="TextItalicUnderline",
                fontName=f"{text_font}-Italic",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_bold_italic_underline = ParagraphStyle(
                name="TextBoldItalicUnderline",
                fontName=f"{text_font}-BoldItalic" if f"{text_font}-BoldItalic" in pdfmetrics.getRegisteredFontNames() else f"{text_font}-Italic",
                fontSize=self.parent.base_font_size if self.parent else 12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            braille_style = ParagraphStyle(
                name="Braille",
                fontName=braille_font,
                fontSize=self.parent.base_font_size if self.parent else 14,  # Utiliser la taille de police de l'interface pour le braille
                spaceAfter=8,
                leading=16,  # Plus d'espacement pour le braille
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )

            # Step 4: Initialize story and pagination parameters
            story = []
            lines_per_page = getattr(self.parent, 'lines_per_page', DEFAULT_LINES_PER_PAGE) if hasattr(self, 'parent') and self.parent else DEFAULT_LINES_PER_PAGE
            line_width = getattr(self.parent, 'line_width', DEFAULT_LINE_WIDTH) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_WIDTH
            indent_mm = getattr(self.parent, 'indent', DEFAULT_INDENT) if hasattr(self, 'parent') and self.parent else DEFAULT_INDENT
            line_spacing = getattr(self.parent, 'line_spacing', DEFAULT_LINE_SPACING) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_SPACING

            # Helper function to wrap text with preserved spaces
            def wrap_text(text, width, allow_break=True):
                """Wrap text to a specified width while preserving spaces."""
                if not text or width < 1:
                    return text
                # Avoid wrapping short texts like "Bienvenue dans le convertisseur"
                if len(text) <= width and not allow_break:
                    logging.debug(f"Text '{text[:50]}...' is short enough, no wrapping applied")
                    return text
                lines = []
                current_line = ""
                words = re.split(r'(\s+)', text)
                for word in words:
                    if not word.strip() and current_line:
                        current_line += word
                    elif len(current_line) + len(word) <= width:
                        current_line += word
                    else:
                        if current_line:
                            lines.append(current_line.rstrip())
                        current_line = word
                if current_line:
                    lines.append(current_line.rstrip())
                wrapped = "<br/>".join(lines)
                logging.debug(f"Wrapped text: {wrapped[:100]}...")
                return wrapped

            # Step 5: Add title with improved formatting
            story.append(Paragraph(f"<para alignment='center'><b>{doc_name}</b></para>", title_style))
            story.append(Spacer(1, 20))  # Plus d'espace après le titre

            # Step 6: Export text content
            if save_type in ["Texte + Braille", "Texte uniquement"]:
                block = text_document.begin()
                block_count = 0
                while block.isValid():
                    if block.text().strip():
                        # Determine alignment
                        align = block.blockFormat().alignment()
                        alignment = TA_LEFT
                        if int(align) & 2:
                            alignment = TA_RIGHT
                        elif int(align) & 4:
                            alignment = TA_CENTER
                        elif int(align) & 8:
                            alignment = TA_JUSTIFY

                        # Build paragraph text with formatting
                        paragraph_parts = []
                        it = block.begin()
                        current_style = []
                        current_text = []
                        while not it.atEnd():
                            fragment = it.fragment()
                            if fragment.isValid():
                                char_format = fragment.charFormat()
                                text = fragment.text()
                                new_style = []
                                if char_format.fontWeight() >= QFont.Bold:
                                    new_style.append("b")
                                if char_format.fontItalic():
                                    new_style.append("i")
                                if char_format.fontUnderline():
                                    new_style.append("u")

                                # If style changes, create a new paragraph part
                                if new_style != current_style:
                                    if current_text:
                                        # Determine the style to use
                                        style_to_use = text_style
                                        if "b" in current_style and "i" in current_style and "u" in current_style:
                                            style_to_use = text_style_bold_italic_underline
                                        elif "b" in current_style and "i" in current_style:
                                            style_to_use = text_style_bold_italic
                                        elif "b" in current_style and "u" in current_style:
                                            style_to_use = text_style_bold_underline
                                        elif "i" in current_style and "u" in current_style:
                                            style_to_use = text_style_italic_underline
                                        elif "b" in current_style:
                                            style_to_use = text_style_bold
                                        elif "i" in current_style:
                                            style_to_use = text_style_italic
                                        elif "u" in current_style:
                                            style_to_use = text_style_underline

                                        # Améliorer la mise en page des paragraphes
                                        style_to_use = ParagraphStyle(
                                            name=f"TextBlock{block_count}_{len(paragraph_parts)}",
                                            parent=style_to_use,
                                            alignment=alignment,
                                            leftIndent=indent_mm * mm,
                                            leading=14 * line_spacing,  # Meilleur espacement des lignes
                                            spaceBefore=4,  # Espace avant le paragraphe
                                            spaceAfter=8,  # Espace après le paragraphe
                                            allowWidows=1,
                                            allowOrphans=1
                                        )

                                        full_text = "".join(current_text)
                                        logging.debug(f"Paragraph part: {full_text[:100]}... with style {style_to_use.name}")
                                        wrapped_text = wrap_text(full_text, line_width, allow_break=len(full_text) > line_width)
                                        
                                        # Obtenir la taille de police du premier fragment du paragraphe pour ce style
                                        # Note : Ceci est une simplification, idéalement il faudrait gérer des tailles mixtes
                                        # au sein d'un même paragraphe si nécessaire, mais reportlab rend cela complexe.
                                        # Pour l'instant, on prend la taille du début du fragment.
                                        first_fragment_char_format = block.begin().fragment().charFormat()
                                        fragment_font_size = first_fragment_char_format.fontPointSize()
                                        
                                        # Appliquer le soulignement en utilisant des balises HTML
                                        if "u" in current_style:
                                            wrapped_text = f"<u>{wrapped_text}</u>"
                                        
                                        paragraph_html = f"<para>{wrapped_text}</para>" if wrapped_text else "<para> </para>"
                                        
                                        # Ajuster la taille de police du style de paragraphe si une taille spécifique est définie
                                        if fragment_font_size > 0:
                                             style_to_use = ParagraphStyle(
                                                name=style_to_use.name, # Conserver le nom
                                                parent=style_to_use, # Hériter des autres propriétés
                                                fontSize=fragment_font_size # Appliquer la taille spécifique
                                            )
                                            
                                        paragraph_parts.append((paragraph_html, style_to_use))
                                        current_text = []
                                current_style = new_style[:]
                                current_text.append(escape(text))
                            it += 1

                        # Add the last part
                        if current_text:
                            style_to_use = text_style
                            if "b" in current_style and "i" in current_style and "u" in current_style:
                                style_to_use = text_style_bold_italic_underline
                            elif "b" in current_style and "i" in current_style:
                                style_to_use = text_style_bold_italic
                            elif "b" in current_style and "u" in current_style:
                                style_to_use = text_style_bold_underline
                            elif "i" in current_style and "u" in current_style:
                                style_to_use = text_style_italic_underline
                            elif "b" in current_style:
                                style_to_use = text_style_bold
                            elif "i" in current_style:
                                style_to_use = text_style_italic
                            elif "u" in current_style:
                                style_to_use = text_style_underline

                            style_to_use = ParagraphStyle(
                                name=f"TextBlock{block_count}_{len(paragraph_parts)}",
                                parent=style_to_use,
                                alignment=alignment,
                                leftIndent=indent_mm * mm,
                                leading=14 * line_spacing,  # Meilleur espacement des lignes
                                spaceBefore=4,  # Espace avant le paragraphe
                                spaceAfter=8,  # Espace après le paragraphe
                                allowWidows=1,
                                allowOrphans=1
                            )

                            full_text = "".join(current_text)
                            logging.debug(f"Final paragraph part: {full_text[:100]}... with style {style_to_use.name}")
                            wrapped_text = wrap_text(full_text, line_width, allow_break=len(full_text) > line_width)
                            
                            # Obtenir la taille de police du dernier fragment du paragraphe pour ce style
                            # Note : Ceci est une simplification.
                            last_fragment_char_format = it.fragment().charFormat()
                            fragment_font_size = last_fragment_char_format.fontPointSize()
                            
                            # Appliquer le soulignement en utilisant des balises HTML
                            if "u" in current_style:
                                wrapped_text = f"<u>{wrapped_text}</u>"
                            
                            paragraph_html = f"<para>{wrapped_text}</para>" if wrapped_text else "<para> </para>"
                            
                            # Ajuster la taille de police du style de paragraphe si une taille spécifique est définie
                            if fragment_font_size > 0:
                                 style_to_use = ParagraphStyle(
                                    name=style_to_use.name, # Conserver le nom
                                    parent=style_to_use, # Hériter des autres propriétés
                                    fontSize=fragment_font_size # Appliquer la taille spécifique
                                )
                                
                            paragraph_parts.append((paragraph_html, style_to_use))

                        # Add all paragraph parts to the story
                        for html, style in paragraph_parts:
                            story.append(Paragraph(html, style))

                    block = block.next()
                    block_count += 1
                    if block_count % lines_per_page == 0 and block.isValid():
                        story.append(Paragraph("<para>--- Page Break ---</para>", text_style))
                        story.append(PageBreak())

            # Step 7: Export Braille content
            if save_type in ["Texte + Braille", "Braille uniquement"]:
                if save_type == "Texte + Braille":
                    story.append(Spacer(1, 30))  # Plus d'espace avant la section braille
                    story.append(Paragraph("<para alignment='center'><b>=== Section Braille ===</b></para>", text_style))
                    story.append(Spacer(1, 20))

                braille_lines = braille_text.split('\n')
                current_page_lines = []
                line_count = 0
                for line in braille_lines:
                    if line_count >= lines_per_page:
                        story.append(Paragraph("<para>--- Page Break ---</para>", braille_style))
                        story.append(PageBreak())
                        for saved_line in current_page_lines:
                            p_style = ParagraphStyle(
                                name=f"BrailleLine{line_count}",
                                parent=braille_style,
                                leftIndent=indent_mm * mm,
                                leading=16 * line_spacing,  # Plus d'espacement pour le braille
                                spaceBefore=2,
                                spaceAfter=4,
                                allowWidows=1,
                                allowOrphans=1
                            )
                            wrapped_line = wrap_text(saved_line, line_width, allow_break=True)
                            story.append(Paragraph(f"<para>{wrapped_line}</para>", p_style))
                        current_page_lines = []
                        line_count = 0
                    if line.strip():
                        current_page_lines.append(escape(line))
                        line_count += 1

                if current_page_lines:
                    for saved_line in current_page_lines:
                        p_style = ParagraphStyle(
                            name=f"BrailleLine{line_count}",
                            parent=braille_style,
                            leftIndent=indent_mm * mm,
                            leading=16 * line_spacing,  # Plus d'espacement pour le braille
                            spaceBefore=2,
                            spaceAfter=4,
                            allowWidows=1,
                            allowOrphans=1
                        )
                        wrapped_line = wrap_text(saved_line, line_width, allow_break=True)
                        story.append(Paragraph(f"<para>{wrapped_line}</para>", p_style))

            # Step 8: Build the PDF
            logging.debug(f"Exporting PDF to {file_path} with {len(story)} story elements")
            doc.build(story)
            logging.info(f"PDF document exported successfully: {file_path}")

        except Exception as e:
            logging.error(f"Error during PDF export: {str(e)}")
            raise Exception(f"Error during PDF export: {str(e)}")

    def export_docx(self, file_path, text_document, braille_text, save_type, font_name=BRAILLE_FONT_NAME, doc_name="Document"):
        try:
            from docx.shared import Pt, Inches
            from PyQt5.QtGui import QFont
            doc = Document()
            from docx.oxml.ns import qn
            doc.add_heading(doc_name, level=0)
            
            # Configurer les marges du document
            sections = doc.sections
            for section in sections:
                section.left_margin = Inches(10 / 25.4)
                section.right_margin = Inches(10 / 25.4)
                section.top_margin = Inches(10 / 25.4)
                section.bottom_margin = Inches(10 / 25.4)
            
            # Récupérer les paramètres de mise en page
            lines_per_page = self.parent.lines_per_page if self.parent else 25
            line_width = self.parent.line_width if self.parent else 80
            indent_mm = self.parent.indent if self.parent else 0
            line_spacing = self.parent.line_spacing if self.parent else 1.0
            
            # Fonction pour formater le texte selon la largeur de ligne
            def format_text_to_width(text, width):
                if not text or width < 1:
                    return text
                words = text.split()
                lines = []
                current_line = []
                current_length = 0
                
                for word in words:
                    word_length = len(word)
                    if current_length + word_length + len(current_line) <= width:
                        current_line.append(word)
                        current_length += word_length
                    else:
                        if current_line:
                            lines.append(' '.join(current_line))
                        current_line = [word]
                        current_length = word_length
                
                if current_line:
                    lines.append(' '.join(current_line))
                
                return '\n'.join(lines)

            if save_type in ["Texte + Braille", "Texte uniquement"]:
                block = text_document.begin()
                block_count = 0
                while block.isValid():
                    if block.text().strip():
                        p = doc.add_paragraph()
                        align = block.blockFormat().alignment()
                        if int(align) & 2:
                            p.alignment = 2  # RIGHT
                        elif int(align) & 4:
                            p.alignment = 1  # CENTER
                        elif int(align) & 8:
                            p.alignment = 3  # JUSTIFY
                        else:
                            p.alignment = 0  # LEFT
                        
                        # Appliquer le retrait et l'espacement des lignes
                        p.paragraph_format.left_indent = Inches(indent_mm / 25.4)
                        p.paragraph_format.line_spacing = line_spacing
                        
                        it = block.begin()
                        while not it.atEnd():
                            fragment = it.fragment()
                            if fragment.isValid():
                                char_format = fragment.charFormat()
                                text = fragment.text()
                                
                                # Formater le texte selon la largeur de ligne
                                formatted_text = format_text_to_width(text, line_width)
                                
                                run = p.add_run(formatted_text)
                                run.font.name = self.parent.current_font if self.parent else font_name
                                # Utiliser la taille de police spécifique du fragment, sinon la taille de base de l'interface
                                fragment_font_size = char_format.fontPointSize()
                                if fragment_font_size > 0:
                                    run.font.size = Pt(fragment_font_size)
                                else:
                                    run.font.size = Pt(self.parent.base_font_size if self.parent else 12)
                                run.bold = char_format.fontWeight() == QFont.Bold
                                run.italic = char_format.fontItalic()
                                run.underline = char_format.fontUnderline()
                            it += 1
                    
                    block = block.next()
                    block_count += 1
                    if block_count % lines_per_page == 0:
                        doc.add_paragraph("--- Page Break ---")

            if save_type in ["Texte + Braille", "Braille uniquement"]:
                if save_type == "Texte + Braille":
                    doc.add_paragraph("=== Section Braille ===")
                
                braille_lines = braille_text.split('\n')
                current_page_lines = []
                line_count = 0
                
                for line in braille_lines:
                    if line_count >= lines_per_page:
                        doc.add_paragraph("--- Page Break ---")
                        for saved_line in current_page_lines:
                            p = doc.add_paragraph()
                            # Formater la ligne braille selon la largeur
                            formatted_line = format_text_to_width(saved_line, line_width)
                            p.add_run(formatted_line).font.name = font_name
                            p.paragraph_format.left_indent = Inches(indent_mm / 25.4)
                            p.paragraph_format.line_spacing = line_spacing
                        current_page_lines = []
                        line_count = 0
                    
                    if line.strip():
                        current_page_lines.append(line)
                        line_count += 1
                
                if current_page_lines:
                    doc.add_paragraph("--- Page Break ---")
                    for saved_line in current_page_lines:
                        p = doc.add_paragraph()
                        # Formater la ligne braille selon la largeur
                        formatted_line = format_text_to_width(saved_line, line_width)
                        p.add_run(formatted_line).font.name = font_name
                        p.paragraph_format.left_indent = Inches(indent_mm / 25.4)
                        p.paragraph_format.line_spacing = line_spacing

            doc.save(file_path)
            print(f"Document DOCX exporté avec succès : {file_path}")
        except Exception as e:
            raise Exception(f"Erreur lors de l'exportation en DOCX : {str(e)}")

    def export_to_gcode(self, file_path):
        if self.last_gcode is None:
            print("Aucun G-code disponible pour l'exportation.")
            return False
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.last_gcode)
            print(f"G-code exporté avec succès : {file_path}")
            return True
        except Exception as e:
            print(f"Erreur lors de l'exportation du G-code : {str(e)}")
            return False

    def print_content(self, printer, text_content, braille_content):
        try:
            painter = QPainter()
            if not painter.begin(printer):
                print("Erreur : Impossible d'initialiser l'impression.")
                return False

            font = QFont(BRAILLE_FONT_NAME, 12)
            painter.setFont(font)
            lines_per_page = self.parent.lines_per_page if self.parent else 25
            line_width = self.parent.line_width if self.parent else 80
            indent_pixels = (self.parent.indent * 2.83) if self.parent else 0
            line_spacing = self.parent.line_spacing if self.parent else 1.0

            y = 50
            page_height = printer.pageRect().height() - 100
            line_height = painter.fontMetrics().height() * line_spacing
            max_lines_per_page = min(lines_per_page, int(page_height / line_height))

            if text_content.strip():
                text_lines = text_content.split('\n')
                current_page_lines = []
                line_count = 0

                for line in text_lines:
                    if line_count >= max_lines_per_page:
                        printer.newPage()
                        y = 50
                        for saved_line in current_page_lines:
                            wrapped_line = self._wrap_text(saved_line, line_width)
                            painter.drawText(50 + indent_pixels, y, wrapped_line)
                            y += line_height
                        current_page_lines = []
                        line_count = 0
                    if line.strip():
                        current_page_lines.append(line)
                        line_count += 1

                if current_page_lines:
                    printer.newPage()
                    y = 50
                    for saved_line in current_page_lines:
                        wrapped_line = self._wrap_text(saved_line, line_width)
                        painter.drawText(50 + indent_pixels, y, wrapped_line)
                        y += line_height

            if braille_content.strip():
                if text_content.strip():
                    printer.newPage()
                    y = 50
                    painter.drawText(50, y, "=== Section Braille ===")
                    y += line_height * 2

                braille_lines = braille_content.split('\n')
                current_page_lines = []
                line_count = 0

                for line in braille_lines:
                    if line_count >= max_lines_per_page:
                        printer.newPage()
                        y = 50
                        for saved_line in current_page_lines:
                            wrapped_line = self._wrap_text(saved_line, line_width)
                            painter.drawText(50 + indent_pixels, y, wrapped_line)
                            y += line_height
                        current_page_lines = []
                        line_count = 0
                    if line.strip():
                        current_page_lines.append(line)
                        line_count += 1

                if current_page_lines:
                    printer.newPage()
                    y = 50
                    for saved_line in current_page_lines:
                        wrapped_line = self._wrap_text(saved_line, line_width)
                        painter.drawText(50 + indent_pixels, y, wrapped_line)
                        y += line_height

            painter.end()
            print("Contenu imprimé avec succès.")
            return True

        except Exception as e:
            print(f"Erreur lors de l'impression : {str(e)}")
            return False

    def _wrap_text(self, text, max_width):
        logging.debug(f"_wrap_text called with text='{text[:50]}...', max_width={max_width}")
        if not text or max_width < 1:
            return text

        lines = []
        current_line = ""
        segments = re.split(r'(\s+|[^\s]+)', text)
        segments = [s for s in segments if s]

        for segment in segments:
            if segment.isspace():
                if len(current_line) + len(segment) <= max_width:
                    current_line += segment
                else:
                    if current_line:
                        lines.append(current_line.rstrip())
                    current_line = segment.lstrip()
                continue

            if len(current_line) + len(segment) <= max_width:
                current_line += segment
            else:
                if current_line:
                    lines.append(current_line.rstrip())
                    current_line = segment
                else:
                    while len(segment) > max_width:
                        lines.append(segment[:max_width])
                        segment = segment[max_width:]
                    current_line = segment

        if current_line:
            lines.append(current_line.rstrip())

        result = "\n".join(lines)
        logging.debug(f"Wrapped text: {result[:100]}...")
        return result

    def convert_to_gcode(self, text):
        if not text.strip():
            return "; Aucun contenu à convertir en G-code\n"

        gcode_lines = []
        gcode_lines.append("; G-code généré à partir du texte Braille")
        gcode_lines.append("G21 ; Utiliser des unités en millimètres")
        gcode_lines.append("G90 ; Utiliser un positionnement absolu")
        gcode_lines.append("G0 Z5.0 ; Lever l'outil")
        gcode_lines.append("G0 X0 Y0 ; Aller à la position initiale")

        x, y = 0, 0
        for char in text:
            if char == '\n':
                y -= 5
                x = 0
            else:
                gcode_lines.append(f"G0 X{x} Y{y} ; Position pour caractère")
                gcode_lines.append("G1 Z0 ; Abaisser l'outil")
                gcode_lines.append("G1 Z5 ; Lever l'outil")
                x += 2

        gcode_lines.append("G0 X0 Y0 ; Retour à l'origine")
        gcode_lines.append("; Fin du G-code")
        return "\n".join(gcode_lines)