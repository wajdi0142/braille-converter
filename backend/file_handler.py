import os
import pdfplumber
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_UNDERLINE
from docx.enum.style import WD_STYLE_TYPE
from reportlab.lib.units import mm
from PyQt5.QtGui import QPainter, QFont
from PyQt5.QtPrintSupport import QPrinter
from PyQt5.QtCore import Qt
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
            braille_char = braille_table.get(char, ' ')
            if braille_char == ' ' and not char.isspace():
                logging.warning(f"Caractère français non traduisible en Braille: '{char}' (U+{ord(char):04x})")
            braille_text += braille_char
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
            braille_char = braille_table.get(char, ' ')
            if braille_char == ' ' and not char.isspace():
                logging.warning(f"Caractère arabe non traduisible en Braille: '{char}' (U+{ord(char):04x})")
            braille_text += braille_char
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

            # Récupérer les paramètres de pagination
            lines_per_page = getattr(self.parent, 'lines_per_page', DEFAULT_LINES_PER_PAGE) if hasattr(self, 'parent') and self.parent else DEFAULT_LINES_PER_PAGE
            line_width = getattr(self.parent, 'line_width', DEFAULT_LINE_WIDTH) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_WIDTH
            indent_mm = getattr(self.parent, 'indent', DEFAULT_INDENT) if hasattr(self, 'parent') and self.parent else DEFAULT_INDENT
            line_spacing = getattr(self.parent, 'line_spacing', DEFAULT_LINE_SPACING) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_SPACING

            # Configuration des polices
            text_font = TEXT_FONT_NAME
            braille_font = font_name

            # Register text font and its variants
            font_variants = {
                "Times New Roman": "Times New Roman",
                "Times New Roman-Bold": "Times New Roman-Bold",
                "Times New Roman-Italic": "Times New Roman-Italic",
                # Add Italic+Bold variant if available and needed for full compatibility
                # "Times New Roman-BoldItalic": "Times New Roman-BoldItalic",
            }
            
            # Common font paths for Windows (adapt for other OS)
            win_font_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Fonts")

            FONT_FILE_MAP = {
                "Times New Roman": "times.ttf",
                "Times New Roman-Bold": "timesbd.ttf",
                "Times New Roman-Italic": "timesi.ttf",
                "Times New Roman-BoldItalic": "timesbi.ttf",
                BRAILLE_FONT_NAME: "NotoSansSymbols2-Regular.ttf", # Assuming Noto Sans Braille uses this file
            }

            for font_key, font_name_reportlab in font_variants.items():
                if font_name_reportlab not in pdfmetrics.getRegisteredFontNames():
                    font_file = FONT_FILE_MAP.get(font_key)
                    font_path = None
                    if font_file:
                        font_path = os.path.join(win_font_dir, font_file)
                    
                    if font_path and os.path.exists(font_path):
                        try:
                            pdfmetrics.registerFont(TTFont(font_name_reportlab, font_path))
                            logging.debug(f"Font '{font_name_reportlab}' registered successfully from {font_path}")
                        except Exception as e:
                            logging.warning(f"Error registering font '{font_name_reportlab}': {str(e)}")
                            # Attempt to register the base font if variants fail
                            if font_key != text_font and text_font in pdfmetrics.getRegisteredFontNames():
                                logging.warning(f"Using fallback base font '{text_font}' for '{font_name_reportlab}'")
                                # ReportLab handles basic style simulation if font variant is missing, but logging is good
                    else:
                        logging.warning(f"Font file not found for '{font_key}' ('{font_name_reportlab}') at {font_path if font_path else 'N/A'}. Ensure font is installed.")

            # Fallback if Times New Roman fails or braille font fails
            if text_font not in pdfmetrics.getRegisteredFontNames():
                logging.warning(f"Text font '{text_font}' not registered, falling back to '{FALLBACK_FONT}'")
                text_font = FALLBACK_FONT # Use a system default that should exist

            if braille_font not in pdfmetrics.getRegisteredFontNames():
                # Try to find Noto Sans Braille more generically
                braille_font_path = None
                braille_font_files = ["NotoSansBraille-Regular.ttf", "NotoSansSymbols2-Regular.ttf"]
                for bf_file in braille_font_files:
                    test_path = os.path.join(win_font_dir, bf_file)
                    if os.path.exists(test_path):
                        braille_font_path = test_path
                        break

                if braille_font_path and braille_font not in pdfmetrics.getRegisteredFontNames():
                    try:
                        pdfmetrics.registerFont(TTFont(braille_font, braille_font_path))
                        logging.debug(f"Braille font '{braille_font}' registered successfully from {braille_font_path}")
                    except Exception as e:
                        logging.error(f"Error registering Braille font '{braille_font}': {str(e)}. Falling back.")
                        braille_font = FALLBACK_FONT # Fallback if registration fails
                elif braille_font not in pdfmetrics.getRegisteredFontNames():
                    logging.error(f"Braille font '{braille_font}' not found or registered. Ensure Noto Sans Braille is installed.")
                    braille_font = FALLBACK_FONT # Fallback if not found or not registered

            # Définir les styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                name="Title",
                fontName=text_font,
                fontSize=16,
                spaceAfter=20,
                spaceBefore=10,
                alignment=TA_CENTER,
                textColor='#000000'
            )
            text_style = ParagraphStyle(
                name="Text",
                fontName=text_font,
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_bold = ParagraphStyle(
                name="TextBold",
                fontName=f"{text_font}-Bold",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            text_style_italic = ParagraphStyle(
                name="TextItalic",
                fontName=f"{text_font}-Italic",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_underline = ParagraphStyle(
                name="TextUnderline",
                fontName=text_font,
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_bold_italic = ParagraphStyle(
                name="TextBoldItalic",
                fontName=f"{text_font}-BoldItalic" if f"{text_font}-BoldItalic" in pdfmetrics.getRegisteredFontNames() else f"{text_font}-Italic",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            text_style_bold_underline = ParagraphStyle(
                name="TextBoldUnderline",
                fontName=f"{text_font}-Bold",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            text_style_italic_underline = ParagraphStyle(
                name="TextItalicUnderline",
                fontName=f"{text_font}-Italic",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#333333'
            )
            text_style_bold_italic_underline = ParagraphStyle(
                name="TextBoldItalicUnderline",
                fontName=f"{text_font}-BoldItalic" if f"{text_font}-BoldItalic" in pdfmetrics.getRegisteredFontNames() else f"{text_font}-Italic",
                fontSize=12,
                spaceAfter=8,
                leading=14,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )
            braille_style = ParagraphStyle(
                name="Braille",
                fontName=braille_font,
                fontSize=14,
                spaceAfter=8,
                leading=16,
                allowWidows=1,
                allowOrphans=1,
                textColor='#000000'
            )

            # Helper function to wrap text with preserved spaces
            def wrap_text(text, width, allow_break=True):
                """Wrap text to a specified width while preserving spaces."""
                if not text or width < 1:
                    return text
                # Avoid wrapping short texts
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

            # Créer le document PDF
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                leftMargin=15 * mm,
                rightMargin=15 * mm,
                topMargin=20 * mm,
                bottomMargin=20 * mm,
                author=author if author else "Utilisateur non connecté",
                title=doc_name,
                subject="Conversion Texte/Braille",
                creator="Convertisseur Texte ↔ Braille"
            )

            # Liste pour stocker tous les éléments du document
            story = []

            # Ajouter le titre
            story.append(Paragraph(f"<para alignment='center'><b>{doc_name}</b></para>", title_style))
            story.append(Spacer(1, 20))

            # Fonction pour gérer la pagination
            def add_page_break_if_needed(current_lines, max_lines):
                if current_lines >= max_lines:
                    story.append(PageBreak())
                    return 0
                return current_lines

            # Compteur de lignes pour la pagination
            current_lines = 0

            # Exporter le contenu texte
            if save_type in ["Texte + Braille", "Texte uniquement"]:
                block = text_document.begin()
                while block.isValid():
                    if block.text().strip():
                        # Déterminer l'alignement
                        align = block.blockFormat().alignment()
                        alignment = TA_LEFT
                        if int(align) & 2:
                            alignment = TA_RIGHT
                        elif int(align) & 4:
                            alignment = TA_CENTER
                        elif int(align) & 8:
                            alignment = TA_JUSTIFY

                        # Traiter le bloc de texte
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

                                if new_style != current_style:
                                    if current_text:
                                        # Appliquer les styles et ajouter au document
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
                                            name=f"TextBlock_{len(story)}",
                                            parent=style_to_use,
                                            alignment=alignment,
                                            leftIndent=indent_mm * mm,
                                            leading=14 * line_spacing,
                                            spaceBefore=4,
                                            spaceAfter=8,
                                            allowWidows=1,
                                            allowOrphans=1
                                        )

                                        full_text = "".join(current_text)
                                        wrapped_text = wrap_text(full_text, line_width, allow_break=len(full_text) > line_width)
                                        
                                        if "u" in current_style:
                                            wrapped_text = f"<u>{wrapped_text}</u>"
                                        
                                        paragraph_html = f"<para>{wrapped_text}</para>" if wrapped_text else "<para> </para>"
                                        story.append(Paragraph(paragraph_html, style_to_use))
                                        
                                        # Mettre à jour le compteur de lignes
                                        current_lines += len(wrapped_text.split('<br/>'))
                                        current_lines = add_page_break_if_needed(current_lines, lines_per_page)
                                        
                                        current_text = []
                                current_style = new_style[:]
                                current_text.append(escape(text))
                            it += 1

                        # Traiter le dernier fragment
                        if current_text:
                            # (Même code que ci-dessus pour le dernier fragment)
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
                                name=f"TextBlock_{len(story)}",
                                parent=style_to_use,
                                alignment=alignment,
                                leftIndent=indent_mm * mm,
                                leading=14 * line_spacing,
                                spaceBefore=4,
                                spaceAfter=8,
                                allowWidows=1,
                                allowOrphans=1
                            )

                            full_text = "".join(current_text)
                            wrapped_text = wrap_text(full_text, line_width, allow_break=len(full_text) > line_width)
                            
                            if "u" in current_style:
                                wrapped_text = f"<u>{wrapped_text}</u>"
                            
                            paragraph_html = f"<para>{wrapped_text}</para>" if wrapped_text else "<para> </para>"
                            story.append(Paragraph(paragraph_html, style_to_use))
                            
                            # Mettre à jour le compteur de lignes
                            current_lines += len(wrapped_text.split('<br/>'))
                            current_lines = add_page_break_if_needed(current_lines, lines_per_page)

                    block = block.next()

            # Ajouter un saut de page entre le texte et le braille si nécessaire
                if save_type == "Texte + Braille":
                    story.append(PageBreak())
                    story.append(Spacer(1, 30))
                    story.append(Paragraph("<para alignment='center'><b>=== Section Braille ===</b></para>", text_style))
                    story.append(Spacer(1, 20))
                current_lines = 0

            # Exporter le contenu braille
            if save_type in ["Texte + Braille", "Braille uniquement"]:
                braille_lines = braille_text.split('\n')
                for line in braille_lines:
                    if line.strip():
                        p_style = ParagraphStyle(
                            name=f"BrailleLine_{len(story)}",
                            parent=braille_style,
                            leftIndent=indent_mm * mm,
                            leading=16 * line_spacing,
                            spaceBefore=2,
                            spaceAfter=4,
                            allowWidows=1,
                            allowOrphans=1
                        )
                        wrapped_line = wrap_text(line, line_width, allow_break=True)
                        story.append(Paragraph(f"<para>{wrapped_line}</para>", p_style))

                        # Mettre à jour le compteur de lignes
                        current_lines += len(wrapped_line.split('<br/>'))
                        current_lines = add_page_break_if_needed(current_lines, lines_per_page)

            # Générer le PDF
            doc.build(story)

        except Exception as e:
            logging.error(f"Erreur lors de l'exportation PDF : {str(e)}")
            raise

    def export_docx(self, file_path, text_document, braille_text, save_type, font_name=BRAILLE_FONT_NAME, doc_name="Document"):
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

            # Récupérer les paramètres de pagination
            lines_per_page = getattr(self.parent, 'lines_per_page', DEFAULT_LINES_PER_PAGE) if hasattr(self, 'parent') and self.parent else DEFAULT_LINES_PER_PAGE
            line_width = getattr(self.parent, 'line_width', DEFAULT_LINE_WIDTH) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_WIDTH
            indent_mm = getattr(self.parent, 'indent', DEFAULT_INDENT) if hasattr(self, 'parent') and self.parent else DEFAULT_INDENT
            line_spacing = getattr(self.parent, 'line_spacing', DEFAULT_LINE_SPACING) if hasattr(self, 'parent') and self.parent else DEFAULT_LINE_SPACING

            # Créer le document Word
            doc = Document()
            
            # Configuration des styles
            styles = doc.styles
            
            # Style du titre
            title_style = styles['Title']
            title_style.font.name = TEXT_FONT_NAME
            title_style.font.size = Pt(16)
            title_style.paragraph_format.space_after = Pt(20)
            title_style.paragraph_format.space_before = Pt(10)
            title_style.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
            
            # Style du texte normal
            text_style = styles['Normal']
            text_style.font.name = TEXT_FONT_NAME
            text_style.font.size = Pt(12)
            text_style.paragraph_format.space_after = Pt(8)
            text_style.paragraph_format.line_spacing = line_spacing
            text_style.paragraph_format.first_line_indent = Pt(indent_mm)
            
            # Style du texte en gras
            bold_style = styles.add_style('Bold', WD_STYLE_TYPE.PARAGRAPH)
            bold_style.font.name = TEXT_FONT_NAME
            bold_style.font.size = Pt(12)
            bold_style.font.bold = True
            bold_style.paragraph_format.space_after = Pt(8)
            bold_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en italique
            italic_style = styles.add_style('Italic', WD_STYLE_TYPE.PARAGRAPH)
            italic_style.font.name = TEXT_FONT_NAME
            italic_style.font.size = Pt(12)
            italic_style.font.italic = True
            italic_style.paragraph_format.space_after = Pt(8)
            italic_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte souligné
            underline_style = styles.add_style('Underline', WD_STYLE_TYPE.PARAGRAPH)
            underline_style.font.name = TEXT_FONT_NAME
            underline_style.font.size = Pt(12)
            underline_style.font.underline = WD_UNDERLINE.SINGLE
            underline_style.paragraph_format.space_after = Pt(8)
            underline_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en gras et italique
            bold_italic_style = styles.add_style('BoldItalic', WD_STYLE_TYPE.PARAGRAPH)
            bold_italic_style.font.name = TEXT_FONT_NAME
            bold_italic_style.font.size = Pt(12)
            bold_italic_style.font.bold = True
            bold_italic_style.font.italic = True
            bold_italic_style.paragraph_format.space_after = Pt(8)
            bold_italic_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en gras et souligné
            bold_underline_style = styles.add_style('BoldUnderline', WD_STYLE_TYPE.PARAGRAPH)
            bold_underline_style.font.name = TEXT_FONT_NAME
            bold_underline_style.font.size = Pt(12)
            bold_underline_style.font.bold = True
            bold_underline_style.font.underline = WD_UNDERLINE.SINGLE
            bold_underline_style.paragraph_format.space_after = Pt(8)
            bold_underline_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en italique et souligné
            italic_underline_style = styles.add_style('ItalicUnderline', WD_STYLE_TYPE.PARAGRAPH)
            italic_underline_style.font.name = TEXT_FONT_NAME
            italic_underline_style.font.size = Pt(12)
            italic_underline_style.font.italic = True
            italic_underline_style.font.underline = WD_UNDERLINE.SINGLE
            italic_underline_style.paragraph_format.space_after = Pt(8)
            italic_underline_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en gras, italique et souligné
            bold_italic_underline_style = styles.add_style('BoldItalicUnderline', WD_STYLE_TYPE.PARAGRAPH)
            bold_italic_underline_style.font.name = TEXT_FONT_NAME
            bold_italic_underline_style.font.size = Pt(12)
            bold_italic_underline_style.font.bold = True
            bold_italic_underline_style.font.italic = True
            bold_italic_underline_style.font.underline = WD_UNDERLINE.SINGLE
            bold_italic_underline_style.paragraph_format.space_after = Pt(8)
            bold_italic_underline_style.paragraph_format.line_spacing = line_spacing
            
            # Style du texte en braille
            braille_style = styles.add_style('Braille', WD_STYLE_TYPE.PARAGRAPH)
            braille_style.font.name = font_name
            braille_style.font.size = Pt(14)
            braille_style.paragraph_format.space_after = Pt(8)
            braille_style.paragraph_format.line_spacing = line_spacing

            # Ajouter le titre
            title = doc.add_heading(doc_name, level=1)
            title.style = title_style

            # Helper function to wrap text with preserved spaces
            def wrap_text(text, width, allow_break=True):
                """Wrap text to a specified width while preserving spaces."""
                if not text or width < 1:
                    return text
                if len(text) <= width and not allow_break:
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
                return "\n".join(lines)

            # Exporter le contenu texte
            if save_type in ["Texte + Braille", "Texte uniquement"]:
                block = text_document.begin()
                while block.isValid():
                    if block.text().strip():
                        # Déterminer l'alignement
                        align = block.blockFormat().alignment()
                        alignment = WD_ALIGN_PARAGRAPH.LEFT
                        if align == Qt.AlignCenter:
                            alignment = WD_ALIGN_PARAGRAPH.CENTER
                        elif align == Qt.AlignRight:
                            alignment = WD_ALIGN_PARAGRAPH.RIGHT
                        elif align == Qt.AlignJustify:
                            alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                        # Créer le paragraphe
                        p = doc.add_paragraph()
                        p.alignment = alignment

                        # Appliquer le style de base
                        p.style = text_style

                        # Traiter les fragments de texte avec leurs styles
                        block_layout = block.layout()
                        if not block_layout:
                            p.style = text_style
                            p.add_run(text)
                            continue

                        for fragment in block.textFormats():
                            text = fragment.text
                            char_format = fragment.format
                            # Appliquer le style approprié
                            if char_format.fontWeight() == QFont.Bold and char_format.fontItalic() and char_format.fontUnderline():
                                p.style = bold_italic_underline_style
                            elif char_format.fontWeight() == QFont.Bold and char_format.fontItalic():
                                p.style = bold_italic_style
                            elif char_format.fontWeight() == QFont.Bold and char_format.fontUnderline():
                                p.style = bold_underline_style
                            elif char_format.fontItalic() and char_format.fontUnderline():
                                p.style = italic_underline_style
                            elif char_format.fontWeight() == QFont.Bold:
                                p.style = bold_style
                            elif char_format.fontItalic():
                                p.style = italic_style
                            elif char_format.fontUnderline():
                                p.style = underline_style
                        else:
                                p.style = text_style
                                p.add_run(text)

                    block = block.next()

            # Ajouter une page de séparation si nécessaire
                if save_type == "Texte + Braille":
                    doc.add_page_break()

            # Exporter le contenu braille
            if save_type in ["Texte + Braille", "Braille uniquement"]:
                # Ajouter un titre pour la section braille
                braille_title = doc.add_heading("Texte en Braille", level=2)
                braille_title.style = title_style

                # Traiter le texte braille ligne par ligne
                for line in braille_text.split('\n'):
                    if line.strip():
                        p = doc.add_paragraph()
                        p.style = braille_style
                        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
                        p.add_run(line)

            # Sauvegarder le document
            doc.save(file_path)
            logging.info(f"Document Word sauvegardé avec succès : {file_path}")

        except Exception as e:
            logging.error(f"Erreur lors de l'exportation en Word : {str(e)}")
            raise Exception(f"Erreur lors de l'exportation en Word : {str(e)}")

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