from issuer.models import BadgeClass, BadgeInstance
from badgeuser.models import BadgeUser
from mainsite.utils import get_name
from mainsite.badge_pdf import BadgePDFCreator
from .badge_pdf import TemplateBadgePDFCreator


def pdfeditor_generate_pdf_content(self, slug, base_url):
    if slug is None:
        raise ValueError("Missing slug parameter")

    try:
        badgeinstance = BadgeInstance.objects.get(entity_id=slug)
    except BadgeInstance.DoesNotExist:
        raise ValueError("BadgeInstance not found")
    try:
        badgeclass = BadgeClass.objects.get(
            entity_id=badgeinstance.badgeclass.entity_id
        )
    except BadgeClass.DoesNotExist:
        raise ValueError("BadgeClass not found")

    try:
        get_name(badgeinstance)
    except BadgeUser.DoesNotExist:
        logger.warning("Could not find badgeuser '%s'", slug)

    if hasattr(badgeinstance, "pdfeditorbadgeinstance") and badgeinstance.pdfeditorbadgeinstance.pdftemplate is not None:
        pdf_creator = TemplateBadgePDFCreator(badgeinstance, badgeclass, origin=base_url)
        pdf_content = pdf_creator.generate_pdf()
    else:
        pdf_creator = BadgePDFCreator()
        pdf_content = pdf_creator.generate_pdf(
            badgeinstance, badgeclass, origin=base_url
        )

    return pdf_content
