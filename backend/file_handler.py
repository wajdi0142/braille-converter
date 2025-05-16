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
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER, TA_JUSTIFY
from xml.sax.saxutils import escape

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration des polices
BRAILLE_FONT_NAME = "Noto Sans Braille"
TEXT_FONT_NAME = "Helvetica"  # Font with bold/italic support
FALLBACK_FONT = "Helvetica"
FONT_PATH = os.getenv("FONT_PATH", r"C:\Users\LENOVO\Downloads\Noto_Sans_Symbols_2\NotoSansBraille-Regular.ttf")

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
        try:
            # Step 1: Font handling
            text_font = TEXT_FONT_NAME  # Use Helvetica for text (supports bold/italic)
            braille_font = font_name
            font_paths = {
                "Helvetica": "C:/Windows/Fonts/helveticaneue.ttf",  # Exemple pour Windows
                "Noto Sans Braille": "C:/Users/LENOVO/Downloads/Noto_Sans_Symbols_2/NotoSansBraille-Regular.ttf"  # Ajuster ce chemin
            }

            # Register text font (Helvetica, which supports bold/italic)
            if text_font not in pdfmetrics.getRegisteredFontNames():
                logging.debug(f"Text font {text_font} not registered, using fallback {FALLBACK_FONT}")
                text_font = FALLBACK_FONT

            # Register Braille font
            if braille_font not in pdfmetrics.getRegisteredFontNames():
                font_path = font_paths.get(braille_font)
                if font_path and os.path.exists(font_path):
                    try:
                        pdfmetrics.registerFont(TTFont(braille_font, font_path))
                        logging.debug(f"Police '{braille_font}' enregistrée avec succès depuis {font_path}")
                    except Exception as e:
                        logging.error(f"Erreur lors de l'enregistrement de la police '{braille_font}': {str(e)}")
                        braille_font = FALLBACK_FONT
                else:
                    logging.warning(f"Police '{braille_font}' non trouvée à {font_path}, utilisation de '{FALLBACK_FONT}'")
                    braille_font = FALLBACK_FONT

            if braille_font not in pdfmetrics.getRegisteredFontNames():
                logging.warning(f"Police '{braille_font}' non disponible, utilisation de '{FALLBACK_FONT}'")
                braille_font = FALLBACK_FONT

            # Step 2: Configure PDF document
            doc = SimpleDocTemplate(
                file_path,
                pagesize=A4,
                leftMargin=10 * mm,
                rightMargin=10 * mm,
                topMargin=10 * mm,
                bottomMargin=10 * mm,
                author=author if author else "Utilisateur non connecté",
                title=doc_name,
                subject="Conversion Texte/Braille",
                creator="Convertisseur Texte ↔ Braille"
            )

            # Step 3: Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                name="Title",
                fontName=text_font,
                fontSize=14,
                spaceAfter=12,
                alignment=TA_CENTER
            )
            text_style = ParagraphStyle(
                name="Text",
                fontName=text_font,
                fontSize=12,
                spaceAfter=6,
                leading=12 * 1.2
            )
            braille_style = ParagraphStyle(
                name="Braille",
                fontName=braille_font,
                fontSize=12,
                spaceAfter=6,
                leading=12 * 1.2
            )

            # Step 4: Initialize story and pagination parameters
            story = []
            lines_per_page = self.parent.lines_per_page if hasattr(self, 'parent') and self.parent else 25
            line_width = self.parent.line_width if hasattr(self, 'parent') and self.parent else 80
            indent_mm = self.parent.indent if hasattr(self, 'parent') and self.parent else 0
            line_spacing = self.parent.line_spacing if hasattr(self, 'parent') and self.parent else 1.0

            # Helper function to wrap text
            def _wrap_text(self, text, width):
                """Wrap text to a specified width."""
                if not text:
                    return ""
                words = text.split()
                lines = []
                current_line = ""
                for word in words:
                    if len(current_line) + len(word) + 1 <= width:
                        current_line += (word + " ") if current_line else word
                    else:
                        lines.append(current_line.rstrip())
                        current_line = word + " "
                if current_line:
                    lines.append(current_line.rstrip())
                return "<br/>".join(lines)

            # Step 5: Add title
            story.append(Paragraph(doc_name, title_style))
            story.append(Spacer(1, 12))

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

                        # Create paragraph style
                        p_style = ParagraphStyle(
                            name=f"TextBlock{block_count}",
                            parent=text_style,
                            alignment=alignment,
                            leftIndent=indent_mm * mm,
                            leading=12 * line_spacing
                        )

                        # Build paragraph text with formatting
                        paragraph_text = []
                        it = block.begin()
                        current_style = []
                        while not it.atEnd():
                            fragment = it.fragment()
                            if fragment.isValid():
                                char_format = fragment.charFormat()
                                text = fragment.text()
                                new_style = []
                                if char_format.fontWeight() == QFont.Bold:
                                    new_style.append("b")
                                if char_format.fontItalic():
                                    new_style.append("i")
                                if char_format.fontUnderline():
                                    new_style.append("u")

                                # Handle style changes
                                for style in new_style:
                                    if style not in current_style:
                                        paragraph_text.append(f"<{style}>")
                                        current_style.append(style)
                                for style in current_style[:]:
                                    if style not in new_style:
                                        paragraph_text.append(f"</{style}>")
                                        current_style.remove(style)

                                paragraph_text.append(escape(text))
                                current_style = new_style[:]
                            it += 1

                        # Close remaining tags
                        for style in current_style[::-1]:
                            paragraph_text.append(f"</{style}>")

                        full_text = "".join(paragraph_text)
                        logging.debug(f"Paragraph text: {full_text[:100]}...")
                        wrapped_text = self._wrap_text(full_text, line_width)
                        paragraph_html = f"<para>{wrapped_text}</para>" if wrapped_text else "<para> </para>"
                        story.append(Paragraph(paragraph_html, p_style))

                    block = block.next()
                    block_count += 1
                    if block_count % lines_per_page == 0 and block.isValid():
                        story.append(Paragraph("<para>--- Page Break ---</para>", text_style))
                        story.append(PageBreak())

            # Step 7: Export Braille content
            if save_type in ["Texte + Braille", "Braille uniquement"]:
                if save_type == "Texte + Braille":
                    story.append(Spacer(1, 24))
                    story.append(Paragraph("<para>=== Section Braille ===</para>", text_style))
                    story.append(Spacer(1, 24))

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
                                leading=12 * line_spacing
                            )
                            wrapped_line = self._wrap_text(saved_line, line_width)
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
                            leading=12 * line_spacing
                        )
                        wrapped_line = self._wrap_text(saved_line, line_width)
                        story.append(Paragraph(f"<para>{wrapped_line}</para>", p_style))

            # Step 8: Build the PDF
            logging.debug(f"Exporting PDF to {file_path} with {len(story)} story elements")
            doc.build(story)
            print(f"Document PDF exporté avec succès : {file_path}")

        except Exception as e:
            logging.error(f"Erreur lors de l'exportation en PDF : {str(e)}")
            raise Exception(f"Erreur lors de l'exportation en PDF : {str(e)}")

    def export_docx(self, file_path, text_document, braille_text, save_type, font_name=BRAILLE_FONT_NAME, doc_name="Document"):
        try:
            from docx.shared import Pt, Inches
            from PyQt5.QtGui import QFont
            doc = Document()
            from docx.oxml.ns import qn
            # Ajouter le titre du document
            doc.add_heading(doc_name, level=0)
            sections = doc.sections
            for section in sections:
                section.left_margin = Inches(10 / 25.4)
                section.right_margin = Inches(10 / 25.4)
                section.top_margin = Inches(10 / 25.4)
                section.bottom_margin = Inches(10 / 25.4)
            lines_per_page = self.parent.lines_per_page if self.parent else 25
            line_width = self.parent.line_width if self.parent else 80
            indent_mm = self.parent.indent if self.parent else 0
            line_spacing = self.parent.line_spacing if self.parent else 1.0
            if save_type in ["Texte + Braille", "Texte uniquement"]:
                block = text_document.begin()
                block_count = 0
                while block.isValid():
                    if block.text().strip():
                        p = doc.add_paragraph()
                        # Alignement
                        align = block.blockFormat().alignment()
                        if int(align) & 2:
                            p.alignment = 2  # RIGHT
                        elif int(align) & 4:
                            p.alignment = 1  # CENTER
                        elif int(align) & 8:
                            p.alignment = 3  # JUSTIFY
                        else:
                            p.alignment = 0  # LEFT
                        p.paragraph_format.left_indent = Inches(indent_mm / 25.4)
                        p.paragraph_format.line_spacing = line_spacing
                        it = block.begin()
                        while not it.atEnd():
                            fragment = it.fragment()
                            if fragment.isValid():
                                char_format = fragment.charFormat()
                                run = p.add_run(fragment.text())
                                run.font.name = font_name
                                run.font.size = Pt(12)
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
                            p = doc.add_paragraph(saved_line)
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
                        p = doc.add_paragraph(saved_line)
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
        segments = [s for s in segments if s]  # Supprime les segments vides

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