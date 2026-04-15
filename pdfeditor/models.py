from django.db import models
from django.conf import settings
from mainsite.mixins import (
    PngImagePreview,
    ScrubUploadedSvgImage,
)
from entity.models import BaseVersionedEntity
from issuer.models import (
    BaseAuditedModel,
    Issuer,
    BadgeInstance,
    QrCode,
    LearningPath,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from mainsite.models import IframeUrl

class PDFTemplate(
    ScrubUploadedSvgImage,
    PngImagePreview,
    BaseVersionedEntity,
    BaseAuditedModel
):
    ALIGNMENT_LEFT = TA_LEFT
    ALIGNMENT_CENTER = TA_CENTER
    ALIGNMENT_CHOICES = (
        (ALIGNMENT_LEFT, "Left"),
        (ALIGNMENT_CENTER, "Center")
    )

    FORMAT_PORTRAIT = 0
    FORMAT_LANDSCAPE = 1
    FORMAT_CHOICES = (
        (FORMAT_PORTRAIT, "Portrait"),
        (FORMAT_LANDSCAPE, "Landscape")
    )

    POSX_DEFAULT = 80
    POSX_MINIMUM = 0
    POSX_MAXIMUM = 1123

    POSY_DEFAULT = 98
    POSY_MINIMUM = 0
    POSY_MAXIMUM = 1123

    SCALE_DEFAULT = 90
    SCALE_MINIMUM = 83
    SCALE_MAXIMUM = 100

    name = models.CharField(max_length=254, blank=False, null=False)
    format = models.IntegerField(
        choices=FORMAT_CHOICES, default=FORMAT_PORTRAIT
    )
    alignment = models.IntegerField(
        choices=ALIGNMENT_CHOICES, default=ALIGNMENT_LEFT
    )
    posX = models.PositiveSmallIntegerField(default=POSX_DEFAULT)
    posY = models.PositiveSmallIntegerField(default=POSY_DEFAULT)
    scale = models.PositiveSmallIntegerField(default=SCALE_DEFAULT)
    image = models.FileField(upload_to="uploads/pdftemplates", blank=True)
    issuer = models.ForeignKey(
        Issuer,
        blank=False,
        null=False,
        on_delete=models.CASCADE,
        related_name="pdftemplates",
    )
    slug = models.CharField(
        max_length=255, db_index=True, blank=True, null=True, default=None
    )

    @property
    def cached_issuer(self):
        return Issuer.cached.get(pk=self.issuer_id)

    def get_absolute_url(self):
        return reverse("pdftemplate_json", kwargs={"entity_id": self.entity_id})

    @property
    def is_used(self):
        if PDFEditorBadgeInstance.objects.filter(pdftemplate=self).count() > 0 or PDFEditorQrCode.objects.filter(pdftemplate=self).count() > 0:
            return True
        return False


class PDFEditorBadgeInstance(models.Model):
    badgeinstance = models.OneToOneField(BadgeInstance, on_delete=models.CASCADE, related_name="pdfeditorbadgeinstance")
    pdftemplate = models.ForeignKey(
        PDFTemplate, blank=True, null=True, on_delete=models.SET_NULL
    )


class PDFEditorQrCode(models.Model):
    qrcode = models.OneToOneField(QrCode, on_delete=models.CASCADE, related_name="pdfeditorqrcode")
    pdftemplate = models.ForeignKey(
        PDFTemplate, blank=True, null=True, on_delete=models.SET_NULL
    )


class PDFEditorLearningPath(models.Model):
    learningpath = models.OneToOneField(LearningPath, on_delete=models.CASCADE, related_name="pdfeditorlearningpath")
    pdftemplate = models.ForeignKey(
        PDFTemplate, blank=True, null=True, on_delete=models.SET_NULL
    )


class PDFEditorIframeUrl(IframeUrl):
    @property
    def url(self):
        baseUrl = getattr(settings, "HTTP_ORIGIN", "http://localhost:8000")
        return f"{baseUrl}/pdfeditor-iframes/{self.id}/"
