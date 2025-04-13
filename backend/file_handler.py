import os
import pdfplumber
import docx
import docx.shared
import cv2
import numpy as np
from PIL import Image, ImageEnhance
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from PyQt5.QtGui import QFont, QTextCursor, QTextCharFormat, QPainter
from PyQt5.QtCore import Qt
from PyQt5.QtPrintSupport import QPrinter
import pytesseract
from .config import BRAILLE_FONT_NAME as CONFIG_BRAILLE_FONT_NAME, FALLBACK_FONT, FONT_PATH
from .braille_engine import BrailleEngine

class FileHandler:
    def __init__(self):
        self.braille_engine = BrailleEngine()
        self.braille_font_name = self._register_font()
        self.last_gcode = None
        self.parent = None

    def extract_text(self, file_path):
        if file_path.endswith(".pdf"):
            try:
                with pdfplumber.open(file_path) as pdf:
                    return "".join(page.extract_text() or "" for page in pdf.pages).strip() or "Aucun texte extrait."
            except Exception as e:
                print(f"Erreur extraction PDF : {e}")
                return ""
        elif file_path.endswith(".docx"):
            try:
                doc = docx.Document(file_path)
                return "\n".join(para.text for para in doc.paragraphs).strip() or "Aucun texte extrait."
            except Exception as e:
                print(f"Erreur extraction Word : {e}")
                return ""
        elif file_path.endswith((".txt", ".bfr")):
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        return "Format non pris en charge."

    def _register_font(self):
        font_name = CONFIG_BRAILLE_FONT_NAME
        try:
            pdfmetrics.registerFont(TTFont(font_name, FONT_PATH))
            print(f"Police {font_name} enregistrée avec succès dans reportlab.")
            return font_name
        except Exception as e:
            print(f"Erreur : {e}. Utilisation de {FALLBACK_FONT}")
            return FALLBACK_FONT

    def image_to_braille(self, image_path, width=40, height=20, mode="hybrid", contrast=1.0, threshold=None):
        try:
            # Lire le fichier image en tant que tableau de bytes pour éviter les problèmes d'encodage de chemin
            with open(image_path, 'rb') as f:
                image_data = np.frombuffer(f.read(), np.uint8)

            # Décoder l'image avec OpenCV
            image = cv2.imdecode(image_data, cv2.IMREAD_GRAYSCALE)
            if image is None:
                raise ValueError("Impossible de charger l'image. Le fichier est peut-être corrompu ou dans un format non supporté.")

            # Conversion en image PIL pour ajuster le contraste
            image_pil = Image.fromarray(image)
            enhancer = ImageEnhance.Contrast(image_pil)
            image_pil = enhancer.enhance(contrast)
            image = np.array(image_pil)

            extracted_text = ""
            braille_text = ""

            if mode in ["text", "hybrid"]:
                try:
                    # Utiliser pytesseract pour extraire le texte
                    extracted_text = pytesseract.image_to_string(image, lang='fra', config='--psm 6 --oem 1')
                    if extracted_text.strip():
                        selected_table = self.braille_engine.get_available_tables().get("Français (grade 1)", "fr-bfu-comp6.utb")
                        braille_text = self.braille_engine.to_braille(extracted_text, selected_table, line_width=width)
                        if mode == "text":
                            return extracted_text, braille_text
                except Exception as e:
                    print(f"Erreur OCR : {e}")

            if mode in ["graphic", "hybrid"]:
                if threshold is None:
                    _, image = cv2.threshold(image, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                else:
                    image = cv2.Canny(image, threshold, threshold * 2)

                image = cv2.resize(image, (width * 2, height * 4))

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

                        dots = 0
                        for i in range(4):
                            for j in range(2):
                                if block[i, j] > 128:
                                    dots |= 1 << (i * 2 + j)
                        braille_char = chr(0x2800 + dots)
                        braille_row.append(braille_char)

                        if dots > 0:
                            has_content = True
                            gcode_x = x / 2.0
                            gcode_y = (height * 4 - y) / 4.0
                            gcode_lines.append(f"G01 X{gcode_x:.2f} Y{gcode_y:.2f} Z-0.1")

                    braille_grid.append(''.join(braille_row))

                gcode_lines.append("M5")
                self.last_gcode = "\n".join(gcode_lines) if has_content else None

                graphic_braille = '\n'.join(braille_grid).strip()
                if mode == "hybrid" and braille_text and graphic_braille:
                    braille_text += "\n\n--- Graphique ---\n" + graphic_braille
                elif mode == "graphic":
                    braille_text = graphic_braille

            if braille_text:
                braille_lines = [line.rstrip() for line in braille_text.split('\n') if line.strip()]
                braille_text = '\n'.join(braille_lines)

            return extracted_text, braille_text if braille_text else ""

        except Exception as e:
            raise ValueError(f"Erreur lors du traitement de l'image : {str(e)}")

    def save_text(self, file_path, text):
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(text)

    def export_pdf(self, file_path, qtext_document, braille, export_choice="Texte + Braille"):
        doc = SimpleDocTemplate(file_path, pagesize=letter, leftMargin=20*mm, rightMargin=20*mm,
                                topMargin=15*mm, bottomMargin=15*mm, title=os.path.basename(file_path),
                                author="Braille Converter App", creator="Braille Converter App")
        styles = getSampleStyleSheet()
        text_style = ParagraphStyle(name='Text', parent=styles['Normal'], fontName="Helvetica", fontSize=12)
        braille_style = ParagraphStyle(name='Braille', parent=styles['Normal'], fontName=self.braille_font_name, fontSize=14)
        content = []
        lines_count = 0
        max_lines = self.parent.lines_per_page if hasattr(self.parent, 'lines_per_page') else 25

        if qtext_document and export_choice in ["Texte + Braille", "Texte uniquement"]:
            for block_idx in range(qtext_document.blockCount()):
                block = qtext_document.findBlockByNumber(block_idx)
                if block.isValid():
                    text = block.text().strip()
                    if text:
                        content.append(Paragraph(text, text_style))
                        lines_count += 1
                        if lines_count >= max_lines:
                            content.append(PageBreak())
                            lines_count = 0

        if braille and export_choice in ["Texte + Braille", "Braille uniquement"]:
            for line in braille.split('\n'):
                content.append(Paragraph(self.braille_engine.wrap_text(line, 40), braille_style))
                lines_count += 1
                if lines_count >= max_lines:
                    content.append(PageBreak())
                    lines_count = 0

        doc.build(content)

    def export_docx(self, file_path, qtext_document, braille, export_choice="Texte + Braille"):
        doc = docx.Document()
        for section in doc.sections:
            section.left_margin = docx.shared.Cm(2)
            section.right_margin = docx.shared.Cm(2)
            section.top_margin = docx.shared.Cm(1.5)
            section.bottom_margin = docx.shared.Cm(1.5)

        if qtext_document and export_choice in ["Texte + Braille", "Texte uniquement"]:
            for block_idx in range(qtext_document.blockCount()):
                block = qtext_document.findBlockByNumber(block_idx)
                if block.isValid():
                    cursor = QTextCursor(block)
                    cursor.select(QTextCursor.BlockUnderCursor)
                    fmt = cursor.charFormat()
                    text = cursor.selectedText().strip()
                    if text:
                        para = doc.add_paragraph()
                        run = para.add_run(text)
                        run.bold = fmt.fontWeight() == QFont.Bold
                        run.italic = fmt.fontItalic()
                        run.underline = fmt.fontUnderline()
                        run.font.size = docx.shared.Pt(fmt.fontPointSize() or 12)
                        run.font.name = fmt.font().family() or "Arial"
                        block_fmt = cursor.blockFormat()
                        if block_fmt.alignment() == Qt.AlignCenter:
                            para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.CENTER
                        elif block_fmt.alignment() == Qt.AlignRight:
                            para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.RIGHT
                        elif block_fmt.alignment() == Qt.AlignLeft:
                            para.alignment = docx.enum.text.WD_ALIGN_PARAGRAPH.LEFT
            doc.add_paragraph()

        if braille and export_choice in ["Texte + Braille", "Braille uniquement"]:
            for line in braille.split('\n'):
                p = doc.add_paragraph()
                run = p.add_run(line)
                run.font.name = self.braille_font_name
                run.font.size = docx.shared.Pt(14)
        doc.save(file_path)

    def export_to_gcode(self, file_path):
        if self.last_gcode is None:
            return False
        with open(file_path, 'w') as f:
            f.write(self.last_gcode)
        return True

    def print_content(self, printer, text, braille):
        painter = QPainter()
        if not painter.begin(printer):
            return False
        font = QFont(self.braille_font_name, 14)
        painter.setFont(font)
        y_pos = 50
        line_height = 30
        max_lines = self.parent.lines_per_page if hasattr(self.parent, 'lines_per_page') else 25
        lines_printed = 0

        if text:
            for line in text.split('\n'):
                painter.drawText(50, y_pos, line)
                y_pos += line_height
                lines_printed += 1
                if lines_printed >= max_lines:
                    printer.newPage()
                    y_pos = 50
                    lines_printed = 0
            y_pos += 20

        if braille:
            for line in braille.split('\n'):
                painter.drawText(50, y_pos, self.braille_engine.wrap_text(line, 40))
                y_pos += line_height
                lines_printed += 1
                if lines_printed >= max_lines:
                    printer.newPage()
                    y_pos = 50
                    lines_printed = 0
        painter.end()
        return True