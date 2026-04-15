from django.contrib.admin import ModelAdmin
from django.utils.safestring import mark_safe
from mainsite.admin import badgr_admin

from .models import (
    PDFTemplate,
    PDFEditorBadgeInstance,
    PDFEditorQrCode,
    PDFEditorLearningPath,
)

class PDFTemplateAdmin(ModelAdmin):
    list_display = (
        "name",
        "format",
        "alignment",
        "posX",
        "posY",
        "scale",
        "background_image",
        "issuer",
        "slug",
        "created_at",
        "created_by"
    )

    def background_image(self, obj):
        try:
            return mark_safe('<img src="{}" width="32"/>'.format(obj.image.url))
        except ValueError:
            return obj.image

    background_image.short_description = "PDF Template Background"
    background_image.allow_tags = True


badgr_admin.register(PDFTemplate, PDFTemplateAdmin)


class PDFEditorBadgeInstanceAdmin(ModelAdmin):
    list_display = ("badgeinstance", "pdftemplate")


badgr_admin.register(PDFEditorBadgeInstance, PDFEditorBadgeInstanceAdmin)


class PDFEditorQrCodeAdmin(ModelAdmin):
    list_display = ("qrcode", "pdftemplate")


badgr_admin.register(PDFEditorQrCode, PDFEditorQrCodeAdmin)


class PDFEditorLearningPathAdmin(ModelAdmin):
    list_display = ("learningpath", "pdftemplate")


badgr_admin.register(PDFEditorLearningPath, PDFEditorLearningPathAdmin)
