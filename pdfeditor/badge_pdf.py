import base64
import math
import os
from functools import partial
from io import BytesIO
from json import loads as json_loads
import cairosvg

from badgeuser.models import BadgeUser
from django.conf import settings
from django.db.models import Max
from issuer.models import BadgeInstance, LearningPath
from mainsite.utils import get_name
from django.core.files.storage import DefaultStorage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader, simpleSplit
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from mainsite.badge_pdf import (
    RoundedImage,
    RoundedRectFlowable,
    PageNumCanvas,
    BadgePDFCreator,
)
from django.utils.translation import activate as activate_language


TEXT_COLOR = "#323232"
ALT_TEXT_COLOR = "#777777"
BACKGROUND_COLOR = "#F5F5F5"

class SimpleCanvas(PageNumCanvas):
    def __init__(self, competencies, fontSize, lineHeight, offsetX, offsetY, *args, **kwargs):
        super(SimpleCanvas, self).__init__(competencies, *args, **kwargs)
        self.pageNumFontSize = fontSize
        self.pageNumLineHeight = lineHeight
        self.pageNumOffsetX = offsetX
        self.pageNumOffsetY = offsetY

    def draw_page_number(self, page_count):
        page = "%s/%s" % (self._pageNumber, page_count)
        page_width = self._pagesize[0]
        self.setFillColor(TEXT_COLOR)
        self.setFont("Rubik-Regular", self.pageNumFontSize)

        self.drawString(
            page_width - self.stringWidth(page) - self.pageNumOffsetX,
            self.pageNumOffsetY + (self.pageNumLineHeight - self.pageNumFontSize) / 2,
            page
        )


class RevisedRoundedRectFlowable(RoundedRectFlowable):
    def __init__(
        self,
        x,
        y,
        width,
        height,
        radius,
        text,
        strokecolor,
        fillcolor,
        studyload,
        max_studyload,
        esco="",
        fontsize=10,
        padding=15,
        iconsize=15,
    ):
        super().__init__(x, y, width, height, radius, text, strokecolor, fillcolor, studyload, max_studyload, esco)
        self.fontsize = fontsize
        self.padding = padding
        self.iconsize = iconsize

    def split_text(self, text, max_width):
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            test_line = f"{current_line} {word}".strip()
            if self.canv.stringWidth(test_line, "Rubik-Regular", self.fontsize) <= max_width:
                current_line = test_line
            else:
                if current_line:
                    lines.append(current_line)
                current_line = word

        lines.append(current_line)
        return lines

    def draw(self):
        self.canv.setFont("Rubik-Medium", self.fontsize)
        max_studyload_width = self.canv.stringWidth(self.max_studyload)

        self.canv.setFillColor(self.fillcolor)
        self.canv.setStrokeColor(self.strokecolor)
        self.canv.roundRect(
            self.x, self.y, self.width, self.height, self.radius, stroke=1, fill=1
        )

        self.canv.setFillColor(TEXT_COLOR)
        self.canv.setFont("Rubik-Regular", self.fontsize)
        self.canv.setFont

        available_text_width = self.width - self.padding - self.padding * 2 - self.iconsize - self.padding / 3 - max_studyload_width - self.padding
        text_lines = self.split_text(self.text, available_text_width)

        y_text_position = 0
        if len(text_lines) == 1:
            spacebetween = (self.height - self.fontsize / 2) / 2
            y_text_position = self.y + spacebetween
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[0]
            )
        elif len(text_lines) == 2:
            spacebetween = (self.height - self.fontsize) / 3
            y_text_position = self.y + 2 * spacebetween + self.fontsize / 2 
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[0]
            )

            y_text_position = spacebetween
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[1]
            )
        else:
            spacebetween = (self.height - 3 * self.fontsize / 2) / 4
            y_text_position = self.y + 3 * spacebetween + self.fontsize
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[0]
            )

            y_text_position = self.y + 2 * spacebetween + self.fontsize / 2 
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[1]
            )

            y_text_position = self.y + spacebetween
            self.canv.drawString(
                self.x + self.padding,
                y_text_position,
                text_lines[2]
            )

        self.canv.setFillColor("blue")
        if self.esco:
            last_line_width = self.canv.stringWidth(text_lines[-1])
            self.canv.drawString(
                self.x + self.padding + last_line_width,
                y_text_position,
                " [E]"
            )
            self.canv.linkURL(
                self.esco,
                (self.x, self.y, self.width, self.height),
                relative=1,
                thickness=0,
            )

        self.canv.setFillColor(TEXT_COLOR)
        self.canv.setFont("Rubik-Medium", self.fontsize)
        studyload_width = self.canv.stringWidth(self.studyload)
        self.canv.drawString(
            self.x + self.width - studyload_width - self.padding,
            self.y + + (self.height - self.fontsize / 2) / 2,
            self.studyload
        )

        clockIcon = ImageReader("{}images/clock-icon_dark.png".format(settings.STATIC_URL))
        self.canv.drawImage(
            clockIcon,
            self.x + self.width - self.iconsize - self.padding / 2 - max_studyload_width - self.padding,
            self.y + (self.height - self.iconsize) / 2,
            width=self.iconsize,
            height=self.iconsize,
            mask="auto",
            preserveAspectRatio=True,
        )


class TemplateBadgePDFCreator(BadgePDFCreator):
    def __init__(self, badge_instance, badge_class, origin):
        super(TemplateBadgePDFCreator, self).__init__()
        self.badge_instance = badge_instance
        self.badge_class = badge_class
        self.origin = origin
        self.pdftemplate = badge_instance.pdfeditorbadgeinstance.pdftemplate
        self.scale = self.pdftemplate.scale / 100

        self.pagesize = A4
        self.blockwidth = 210 * mm * 0.4815
        self.available_height = 297 * mm * 0.8013
        if self.pdftemplate.format == 1:
            self.pagesize = landscape(A4)
            self.blockwidth = 297 * mm * 0.6283
            self.available_height = 210 * mm * 0.926

        self.blockwidth *= self.scale
        self.available_height *= self.scale

        # Doc dimensions to pdf dimensions (px to pt)
        self.pdftemplate.posX *= 0.75
        self.pdftemplate.posY *= 0.75

        self.page = 1

        try:
            self.name = get_name(self.badge_instance)
        except BadgeUser.DoesNotExist:
            self.name = self.badge_instance.recipient_identifier

        extensions = self.badge_class.cached_extensions()
        categoryExtension = extensions.get(name="extensions:CategoryExtension")
        self.category = json_loads(categoryExtension.original_json)["Category"]

    def add_badge_image(self, story, size=160):
        size *= self.scale

        story.append(
            Image(self.badge_class.image, width=size, height=size, hAlign=self.pdftemplate.alignment)
        )
        self.used_space += size

    def add_recipient_name(self, story, fontSize=16, lineHeight=19.2):
        fontSize *= self.scale
        lineHeight *= self.scale

        recipient_style = ParagraphStyle(
            name="Recipient",
            fontSize=fontSize,
            leading=lineHeight,
            fontName="Rubik-Bold",
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        recipient_name = f"<strong>{self.name}</strong>"
        story.append(Paragraph(recipient_name, recipient_style))
        self.used_space += lineHeight

    def add_details(self, story, fontSize=14, lineHeight=18.2):
        fontSize *= self.scale
        lineHeight *= self.scale

        text_style = ParagraphStyle(
            name="Text_Style",
            fontSize=fontSize,
            leading=lineHeight,
            fontName="Rubik-Regular",
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment
        )

        if (
            self.badge_instance.activity_start_date is not None
            and self.badge_instance.activity_end_date is not None
            and self.badge_instance.activity_start_date != self.badge_instance.activity_end_date
        ):
            startdate = self.badge_instance.activity_start_date.strftime("%d.%m.")
            enddate = self.badge_instance.activity_end_date.strftime("%d.%m.%Y")

            text = f"hat vom <font name='Rubik-Medium'>{startdate}–{enddate}</font>"
        elif self.badge_instance.activity_start_date is not None:
            date = self.badge_instance.activity_start_date.strftime("%d.%m.%Y")
            text = f"hat am <font name='Rubik-Medium'>{date}</font>"
        else:
            date = self.badge_instance.issued_on.strftime("%d.%m.%Y")
            text = f"hat am <font name='Rubik-Medium'>{date}</font>"

        if self.badge_instance.activity_city:
            text += f" in <font name='Rubik-Medium'>{self.badge_instance.activity_city}</font>"
        elif self.badge_instance.activity_online:
            text += " <font name='Rubik-Medium'>online</font>"

        story.append(Paragraph(text, text_style))
        self.used_space += lineHeight

        extensions = self.badge_class.cached_extensions()
        studyLoadExtension = extensions.get(name="extensions:StudyLoadExtension")
        studyLoad = json_loads(studyLoadExtension.original_json)["StudyLoad"]

        text = f"innerhalb von <font name='Rubik-Medium'>"
        studyLoadHours = math.floor(studyLoad / 60)
        studyLoadMinutes = studyLoad % 60
        if studyLoadHours > 0:
            text += f"{studyLoadHours} Std."
        if studyLoadHours and studyLoadMinutes:
            text += f" "
        if studyLoadMinutes > 0:
            text += f"{studyLoadMinutes} Min."
        text += f"</font>"
        story.append(Paragraph(text, text_style))
        self.used_space += lineHeight

        text = "folgenden Badge erworben:"
        story.append(Paragraph(text, text_style))
        self.used_space += lineHeight

    def add_title(self, story, fontSize=16, lineHeight=19.2):
        fontSize *= self.scale
        lineHeight *= self.scale

        title_style = ParagraphStyle(
            name="Title",
            fontSize=fontSize,
            leading=lineHeight,
            fontName="Rubik-Bold",
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )
        story.append(
            Paragraph(f"<strong>{self.badge_class.name}</strong>", title_style)
        )
        self.used_space += lineHeight

    def add_description(self, story, fontSize=12, lineHeight=15.6):
        fontSize *= self.scale
        lineHeight *= self.scale

        description_style = ParagraphStyle(
            name="Description",
            fontSize=fontSize,
            leading=lineHeight,
            fontName="Rubik-Regular",
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )
        story.append(Paragraph(self.badge_class.description, description_style))

        num_lines = self.get_line_count(self.badge_class.description, description_style)
        self.used_space += num_lines * lineHeight

    def add_issued_by(self, story, qrSize=50, radius=5, cellPadding=4, fontSize=10, lineHeight=13):
        fontSize *= self.scale
        lineHeight *= self.scale
        qrSize *= self.scale
        cellPadding *= self.scale

        qrCodeImage = self.generate_qr_code(self.badge_instance, self.origin)

        # use document width to calculate the table and its size
        document_width, _ = self.pagesize

        issued_by_style = ParagraphStyle(
            name="IssuedBy",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            fontName="Rubik-Bold",
            alignment=TA_LEFT,
            leftIndent=-3,
        )
        issued_by_text = 'ERSTELLT ÜBER <a href="https://openbadges.education" color="#1400FF" underline="true">OPENBADGES.EDUCATION</a>.'

        issued_by_style_2 = ParagraphStyle(
            name="IssuedBy",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            fontName="Rubik-Regular",
            alignment=TA_LEFT,
            leftIndent=-3,
        )
        issued_by_text_2 = "Der digitale Badge kann über den QR-Code abgerufen werden"

        if qrCodeImage.startswith("data:image"):
            qrCodeImage = qrCodeImage.split(",")[1]  # Entfernt das Präfix

        image = base64.b64decode(qrCodeImage)
        qrCodeImage = BytesIO(image)
        qrCodeImage = ImageReader(qrCodeImage)

        rounded_img = RoundedImage(
            img_path=qrCodeImage,
            width=qrSize - 2 * (1 + 1.8),
            height=qrSize - 2 * (1 + 1.8),
            border_color=TEXT_COLOR,
            border_width=1,
            padding=0,
            radius=radius,
        )

        img_table = Table(
            [[rounded_img, [Paragraph(issued_by_text, issued_by_style), Paragraph(issued_by_text_2, issued_by_style_2)]]],
            colWidths=[qrSize + 2 * cellPadding, self.blockwidth - (qrSize + 2 * cellPadding)],
            rowHeights=[qrSize + 2 * cellPadding]
        )
        img_table.hAlign = "CENTER"
        img_table.setStyle(
            TableStyle(
                [
                    ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                    ("VALIGN", (1, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(BACKGROUND_COLOR)),
                    ("LEFTPADDING", (0, 0), (-1, -1), cellPadding),
                    ("RIGHTPADDING", (0, 0), (-1, -1), cellPadding),
                    ("TOPPADDING", (0, 0), (-1, -1), cellPadding),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), cellPadding),
                    ("ROUNDEDCORNERS", [radius, radius, radius, radius]),
                    # ('GRID', (0, 0), (-1, -1), 0.5, colors.red), # for debugging
                ]
            )
        )

        story.append(img_table)
        self.used_space += qrSize + 2 * cellPadding

    def add_cover_block(self, story):
        self.add_recipient_name(story)
        self.add_spacer(story, 8 * self.scale)
        self.add_details(story)
        self.add_spacer(story, 24 * self.scale)
        self.add_badge_image(story)
        self.add_spacer(story, 20 * self.scale)
        self.add_title(story)
        self.add_spacer(story, 8 * self.scale)
        self.add_description(story)
        self.add_spacer(story, 24 * self.scale)
        self.add_issued_by(story)

    # ----------------------------------------------------- #

    def add_learningpath_desc(self, story, fontSize=12, lineHeight=15.6):
        fontSize *= self.scale
        lineHeight *= self.scale

        text_style = ParagraphStyle(
            name="Text",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        text = f"die <strong>{self.name}</strong> mit dem Micro Degree <strong>{self.badge_class.name}</strong> erworben hat:"
        story.append(Paragraph(text, text_style))
        num_lines = self.get_line_count(text, text_style)
        self.used_space += num_lines * lineHeight

    def add_learningpath_badges(self, story, badges, fontSize=12, lineHeight=14.4, badgeSize=65, space=16):
        fontSize *= self.scale
        lineHeight *= self.scale
        badgeSize *= self.scale
        space *= self.scale

        lp_badge_info_style = ParagraphStyle(
            name="Text",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=TA_LEFT,
        )

        lp_badge_table_style = TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("LEFTPADDING", (1, 0), (1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                # ('GRID', (0, 0), (-1, -1), 0.5, colors.red), # for debugging
            ]
        )

        if len(badges) > 0:
            for badge in badges:
                img = Image(badge.image, width=badgeSize, height=badgeSize)
                badge_title = Paragraph(
                    f"<strong>{badge.badgeclass.name}</strong>", lp_badge_info_style
                )
                issuer = Paragraph(
                    badge.badgeclass.issuer.name, lp_badge_info_style
                )
                date = Paragraph(
                    badge.issued_on.strftime("%d.%m.%Y"), lp_badge_info_style
                )
                data = [[img, [badge_title, Spacer(1, 5), issuer, Spacer(1, 2), date]]]

                table = Table(data, colWidths=[badgeSize, self.blockwidth - badgeSize])
                table.setStyle(lp_badge_table_style)

                tableWidth, tableHeight = table.wrap(0,0)

                if self.used_space + tableHeight > self.available_height:
                    self.add_page_break(story)
                    self.add_learningpath_header(story)

                story.append(table)
                story.append(Spacer(1, space))
                self.used_space += tableHeight + space

    def add_learningpath_header(self, story):
        self.add_headline(story, "Badges")
        self.add_spacer(story, 4 * self.scale)
        self.add_learningpath_desc(story)
        self.add_spacer(story, 16 * self.scale)

    def add_learningpath_block(self, story):
        self.add_learningpath_header(story)

        badges = self.get_learningpath_badges()
        for badge in badges:
            self.append_competencies(badge.badgeclass)

        self.add_learningpath_badges(story, badges)

    # ----------------------------------------------------- #

    def get_competencies_subline_space(self, fontSize=12, lineHeight=15.6):
        fontSize *= self.scale
        lineHeight *= self.scale

        text_style = ParagraphStyle(
            name="Text",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )
        text = f"die <strong>{self.name}</strong> mit dem Badge <strong>{self.badge_class.name}</strong> erworben hat:"

        num_lines = self.get_line_count(text, text_style)
        return num_lines * lineHeight

    def add_competencies_subline(self, story, fontSize=12, lineHeight=15.6):
        fontSize *= self.scale
        lineHeight *= self.scale

        text_style = ParagraphStyle(
            name="Text",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        text = f"die <strong>{self.name}</strong> mit dem Badge <strong>{self.badge_class.name}</strong> erworben hat:"
        story.append(Paragraph(text, text_style))

        num_lines = self.get_line_count(text, text_style)
        self.used_space += num_lines * lineHeight

    def get_competencies_details_min_space(self, height=36):
        height *= self.scale
        return height

    def add_competencies_details(self, story, height=36, radius=8, padding=13, iconsize=13, fontSize=10, space=8):
        fontSize *= self.scale
        space *= self.scale
        height *= self.scale
        padding *= self.scale
        iconsize *= self.scale

        max_studyload = max(c["studyLoad"] for c in self.competencies)
        max_studyload = "%s:%s h" % (
            math.floor(max_studyload / 60),
            str(max_studyload % 60).zfill(2),
        )

        for i in range(len(self.competencies)):
            if self.used_space + space + height > self.available_height:
                self.add_page_break(story)
                self.add_competencies_header(story)

            story.append(Spacer(1, space))

            studyload = "%s:%s h" % (
                math.floor(self.competencies[i]["studyLoad"] / 60),
                str(self.competencies[i]["studyLoad"] % 60).zfill(2),
            )

            rounded_rect = RevisedRoundedRectFlowable(
                0,
                0,
                width=self.blockwidth,
                height=height,
                radius=radius,
                text=self.competencies[i]["name"],
                strokecolor=TEXT_COLOR,
                fillcolor=BACKGROUND_COLOR,
                studyload=studyload,
                max_studyload=max_studyload,
                esco=self.competencies[i]["framework_identifier"],
                fontsize=fontSize,
                padding=padding,
                iconsize=iconsize,
            )
            story.append(rounded_rect)
            self.used_space += height + space

    def add_competencies_header(self, story):
        self.add_headline(story, "Kompetenzen")
        self.add_spacer(story, 4 * self.scale)
        self.add_competencies_subline(story)
        self.add_spacer(story, 8 * self.scale)

    def get_competencies_min_space(self):
        min_space = self.get_headline_space()
        min_space += 4 * self.scale
        min_space += self.get_competencies_subline_space()
        min_space += 16 * self.scale
        min_space += self.get_competencies_details_min_space()
        return min_space

    def add_competencies_block(self, story):
        min_space = self.get_competencies_min_space()
        if self.page == 1 or self.used_space + min_space > self.available_height:
            self.add_page_break(story)

        self.add_competencies_header(story)
        self.add_competencies_details(story)

    # ----------------------------------------------------- #

    def get_criteria_items_min_space(self, fontSizeName=12, lineHeightName=15.6, fontSizeDesc=10, lineHeightDesc=12):
        fontSizeName *= self.scale
        lineHeightName *= self.scale
        fontSizeDesc *= self.scale
        lineHeightDesc *= self.scale

        name_style = ParagraphStyle(
            name="Name",
            fontSize=fontSizeName,
            leading=lineHeightName,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            leftIndent=8*self.scale
        )

        description_style = ParagraphStyle(
            name="Description",
            fontSize=fontSizeDesc,
            leading=lineHeightDesc,
            textColor=ALT_TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            fontName="Rubik-Italic",
        )

        spaceToBeUsed = 0
        for index, item in enumerate(self.badge_class.criteria):
            if "name" in item and item["name"]:
                spaceToBeUsed += lineHeightName
            if "description" in item and item["description"]:
                num_lines = self.get_line_count(item["description"], description_style)
                spaceToBeUsed += num_lines * lineHeightDesc
            break

        return spaceToBeUsed

    def add_criteria_items(self, story, fontSizeName=12, lineHeightName=15.6, fontSizeDesc=10, lineHeightDesc=12):
        fontSizeName *= self.scale
        lineHeightName *= self.scale
        fontSizeDesc *= self.scale
        lineHeightDesc *= self.scale

        name_style = ParagraphStyle(
            name="Name",
            fontSize=fontSizeName,
            leading=lineHeightName,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            leftIndent=8*self.scale
        )

        description_style = ParagraphStyle(
            name="Description",
            fontSize=fontSizeDesc,
            leading=lineHeightDesc,
            textColor=ALT_TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            fontName="Rubik-Italic",
        )

        for index, item in enumerate(self.badge_class.criteria):
            spaceToBeUsed = 0
            if "name" in item and item["name"]:
                spaceToBeUsed += lineHeightName
            if "description" in item and item["description"]:
                num_lines = self.get_line_count(item["description"], description_style)
                spaceToBeUsed += num_lines * lineHeightDesc

            if self.used_space + spaceToBeUsed > self.available_height:
                self.add_page_break(story)
                self.add_criteria_header(story)

            if "name" in item and item["name"]:
                bullet_text = f"• {item['name']}"
                story.append(Paragraph(bullet_text, name_style))
                self.used_space += lineHeightName

            if "description" in item and item["description"]:
                num_lines = self.get_line_count(item["description"], description_style)
                story.append(Paragraph(item["description"], description_style))
                self.add_spacer(story, 4 * self.scale)
                self.used_space += num_lines * lineHeightDesc

    def add_criteria_header(self, story):
        self.add_headline(story, "Vergabe-Kriterien")
        self.add_spacer(story, 4 * self.scale)

    def get_criteria_min_space(self):
        min_space = self.get_headline_space()
        min_space += 4 * self.scale
        min_space += self.get_criteria_items_min_space()
        return min_space

    def add_criteria_block(self, story, space=40):
        space *= self.scale
        min_space = self.get_criteria_min_space()

        if self.used_space + space + min_space > self.available_height:
            self.add_page_break(story)
        else:
            self.add_spacer(story, space)

        self.add_criteria_header(story)
        self.add_criteria_items(story)

    # ----------------------------------------------------- #

    def get_narrative_space(self, fontSize=12, lineHeight=15.6, cutOff=280):
        fontSize *= self.scale
        lineHeight *= self.scale

        narrative_style = ParagraphStyle(
            name="Narrative",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        narratives = [
            item.narrative for item in (self.badge_instance.evidence_items or []) if item.narrative
        ]

        if self.badge_instance.narrative or narratives:
            narrative_text = narratives[0] if narratives else self.badge_instance.narrative
            if len(narrative_text) > cutOff:
                narrative_text = narrative_text[:cutOff] + "..."

            num_lines = self.get_line_count(narrative_text, narrative_style)
            return num_lines * lineHeight + 8 * self.scale

        return 0

    def add_narrative(self, story, fontSize=12, lineHeight=15.6, cutOff=280):
        fontSize *= self.scale
        lineHeight *= self.scale

        narrative_style = ParagraphStyle(
            name="Narrative",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        narratives = [
            item.narrative for item in (self.badge_instance.evidence_items or []) if item.narrative
        ]

        if self.badge_instance.narrative or narratives:
            self.add_spacer(story, 8 * self.scale)

            narrative_text = narratives[0] if narratives else self.badge_instance.narrative

            if len(narrative_text) > cutOff:
                narrative_text = narrative_text[:cutOff] + "..."
            story.append(Paragraph(narrative_text, narrative_style))

            num_lines = self.get_line_count(narrative_text, narrative_style)
            self.used_space += num_lines * lineHeight

    def get_evidence_url_space(self, lineHeight=15.6, space=8):
        evidence_urls = [
            item.evidence_url for item in (self.badge_instance.evidence_items or []) if item.evidence_url
        ]

        spaceToBeUsed = 0
        for url in evidence_urls:
            spaceToBeUsed += space + lineHeight

        return spaceToBeUsed

    def add_evidence_url(self, story, iconsize=15, fontSize=12, lineHeight=15.6, space=8):
        iconsize *= self.scale
        fontSize *= self.scale
        lineHeight *= self.scale
        space *= self.scale

        linknote_style = ParagraphStyle(
            name="LinkNote",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
        )

        icon_path = os.path.join(settings.STATIC_URL, "images/external_link.png")

        evidence_urls = [
            item.evidence_url for item in (self.badge_instance.evidence_items or []) if item.evidence_url
        ]

        for url in evidence_urls:
            self.add_spacer(story, space)

            text = f'<img src="{icon_path}" width="{iconsize}" height="{iconsize}" valign="middle"/> <a href="{url}" color="#1400FF" underline="true">Nachweis-URL</a>'

            story.append(Paragraph(text, linknote_style))
            self.used_space += lineHeight

    def get_narrative_min_space(self):
        min_space = self.get_headline_space()
        min_space += self.get_evidence_url_space()
        min_space += self.get_narrative_space()
        return min_space

    def add_narrative_block(self, story, space=40):
        space *= self.scale
        min_space = self.get_narrative_min_space()

        if self.used_space + space + min_space > self.available_height:
            self.add_page_break(story)
        else:
            self.add_spacer(story, space)

        self.add_headline(story, "Narrativ")
        self.add_evidence_url(story)
        self.add_narrative(story)

    # ----------------------------------------------------- #

    def get_esco_footnote_space(self, lineHeight=11.7):
        lineHeight *= self.scale
        return 3 * lineHeight

    def add_esco_footnote(self, story, fontSize=9, lineHeight=11.7):
        fontSize *= self.scale
        lineHeight *= self.scale

        footnote_style = ParagraphStyle(
            name="Footnote",
            fontSize=fontSize,
            leading=lineHeight,
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            fontName="Rubik-Italic",
        )

        line = '[E] = Kompetenz nach ESCO (European Skills, Competencies, Qualifications and Occupations). Die Kompetenz-Beschreibungen gemäß ESCO sind abrufbar über <a href="https://esco.ec.europa.eu/de" color="#1400FF" underline="true">https://esco.ec.europa.eu/de</a>.'
        story.append(Paragraph(line, footnote_style))
        self.used_space += 3 * lineHeight

    def add_footer_block(self, story, space=40):
        space *= self.scale
        if self.used_space + space + self.get_esco_footnote_space() > self.available_height:
            self.add_page_break(story)
        else:
            self.add_spacer(story, space)

        self.add_esco_footnote(story)

    # ----------------------------------------------------- #

    def get_headline_space(self, lineHeight=24):
        lineHeight *= self.scale
        return lineHeight

    def add_headline(self, story, text, fontSize=16, lineHeight=24):
        fontSize *= self.scale
        lineHeight *= self.scale

        title_style = ParagraphStyle(
            name="Title",
            fontSize=fontSize,
            leading=lineHeight,
            fontName="Rubik-Medium",
            textColor=TEXT_COLOR,
            alignment=self.pdftemplate.alignment,
            textTransform="uppercase",
        )

        story.append(Paragraph(text, title_style))
        self.used_space += lineHeight

    def add_spacer(self, story, space=0):
        story.append(Spacer(1, space))
        self.used_space += space

    def add_page_break(self, story):
        story.append(PageBreak())
        self.used_space = 0
        self.page += 1

    def get_line_count(self, text, style):
        lines = simpleSplit(text, style.fontName, style.fontSize, self.blockwidth)

        return len(lines)

    def get_learningpath_badges(self):
        lp = LearningPath.objects.filter(participationBadge=self.badge_class).first()
        lp_badges = [badge.badge for badge in lp.learningpath_badges]
        badgeuser = BadgeUser.objects.get(email=self.badge_instance.recipient_identifier)
        badge_ids = (
            BadgeInstance.objects.filter(
                badgeclass__in=lp_badges,
                recipient_identifier__in=badgeuser.verified_emails,
            )
            .values("badgeclass")
            .annotate(max_id=Max("id"))
            .values_list("max_id", flat=True)
        )

        return BadgeInstance.objects.filter(id__in=badge_ids)

    def append_competencies(self, badge_class):
        competencies = badge_class.json["extensions:CompetencyExtension"]
        for competency in competencies:
            if competency not in self.competencies:
                self.competencies.append(competency)

    def get_background_image(self, width, height):
        try:
            file_ext = self.pdftemplate.image.path.split(".")[-1].lower()
            if file_ext == "svg":
                storage = DefaultStorage()
                bio = BytesIO()
                file_path = self.pdftemplate.image.name
                try:
                    with storage.open(file_path, "rb") as svg_file:
                        cairosvg.svg2png(file_obj=svg_file, write_to=bio)
                except IOError:
                    raise ValueError(
                        f"Failed to convert SVG to PNG: {self.pdftemplate.image}"
                    )

                bio.seek(0)
                dummy = Image(bio)
                backgroundImageContent = Image(bio, width=width, height=height)
            elif file_ext in ["png", "jpg", "jpeg"]:
                dummy = Image(self.pdftemplate.image)
                try:
                    self.pdftemplate.image.open()
                    img_data = BytesIO(self.pdftemplate.image.read())
                    self.pdftemplate.image.close()
                    backgroundImageContent = Image(img_data, width=width, height=height)
                except Exception as e:
                    print(f"Unexpected error for image {self.pdftemplate.image}: {e}")
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
        except Exception as e:
            backgroundImageContent = None

        return backgroundImageContent

    def background(self, canvas, doc, backgroundImage):
        if backgroundImage is not None:
            canvas.saveState()
            backgroundImage.drawOn(canvas, 0, 0)
            canvas.restoreState()

    def generate_pdf(self):
        activate_language(self.badgeclass.language)
        buffer = BytesIO()

        doc = BaseDocTemplate(
            buffer,
            pagesize=self.pagesize,
            leftMargin=0,
            rightMargin=0,
            topMargin=0,
            bottomMargin=0,
        )

        backgroundImage = self.get_background_image(doc.width, doc.height)

        templateFrame = Frame(
            self.pdftemplate.posX,
            doc.height - self.pdftemplate.posY - self.available_height,
            self.blockwidth, self.available_height,
            0, 0, 0, 0,
            id="templateFrame",
            # showBoundary=1, # for debugging
        )
        templatePage = PageTemplate(
            id="templatePage",
            frames=templateFrame,
            onPage=partial(
                self.background,
                backgroundImage=backgroundImage,
            ),
        )

        doc.addPageTemplates([templatePage])

        self.used_space = 0
        story = []

        self.add_cover_block(story)

        self.append_competencies(self.badge_class)

        if self.category == "learningpath":
            self.add_page_break(story)
            self.add_learningpath_block(story)

        if len(self.competencies) > 0:
            self.add_competencies_block(story)

        if self.badge_class.criteria or \
            self.badge_instance.narrative or \
            self.badge_instance.evidence_items:
                if self.page == 1:
                    self.add_page_break(story)

        if self.badge_class.criteria:
            self.add_criteria_block(story)

        if self.badge_instance.narrative or self.badge_instance.evidence_items:
            self.add_narrative_block(story)

        if len(self.competencies) > 0:
            self.add_footer_block(story)

        doc.build(story, canvasmaker=partial(SimpleCanvas, self.competencies, 10 * self.scale, 15 * self.scale, 40, 36))
        pdfContent = buffer.getvalue()
        buffer.close()
        return pdfContent
