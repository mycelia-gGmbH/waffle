from django.core.exceptions import ObjectDoesNotExist
from issuer.models import LearningPath
from .models import (
    PDFEditorBadgeInstance,
    PDFEditorLearningPath,
)


def handle_badgeinstance_save(sender, instance, created, **kwargs):
    if created:
        lp = None
        pdftemplate = None
        try:
            lp = LearningPath.objects.get(participationBadge=instance.badgeclass)
            pdftemplate = PDFEditorLearningPath.objects.get(learningpath=lp).pdftemplate
        except ObjectDoesNotExist:
            pass

        if lp is not None:
            try:
                pbi = PDFEditorBadgeInstance.objects.get(badgeinstance=instance)
                pbi.pdftemplate = pdftemplate
                pbi.save()
            except ObjectDoesNotExist:
                PDFEditorBadgeInstance.objects.create(
                    badgeinstance=instance,
                    pdftemplate=pdftemplate,
                )
