from django.apps import AppConfig
from django.urls import re_path


class PDFEditorConfig(AppConfig):
    name = "pdfeditor"

    def ready(self):
        # override original generate_pdf_content function and serializers
        from mainsite.account_adapter import BadgrAccountAdapter
        from backpack import views
        from .account_adapter import pdfeditor_generate_pdf_content
        from .views import pdfeditor_backpack_pdf

        BadgrAccountAdapter.generate_pdf_content = pdfeditor_generate_pdf_content

        # override original use of BadgeInstanceSerializerV1
        from issuer.api import (
            BatchAssertionsIssue,
            BadgeInstanceDetail,
            BadgeInstanceList,
        )
        from .serializers_v1 import PDFEditorBadgeInstanceSerializerV1

        BatchAssertionsIssue.v1_serializer_class = PDFEditorBadgeInstanceSerializerV1
        BadgeInstanceDetail.v1_serializer_class = PDFEditorBadgeInstanceSerializerV1
        BadgeInstanceList.v1_serializer_class = PDFEditorBadgeInstanceSerializerV1

        # override original use of QrCodeSerializerV1
        from issuer.api import QRCodeDetail, QRCodeList
        from .serializers_v1 import PDFEditorQrCodeSerializerV1

        QRCodeList.v1_serializer_class = PDFEditorQrCodeSerializerV1
        QRCodeDetail.v1_serializer_class = PDFEditorQrCodeSerializerV1

        # override original use of LearningPathSerializerV1
        from issuer.api import LearningPathDetail, IssuerLearningPathList
        from .serializers_v1 import PDFEditorLearningPathSerializerV1

        IssuerLearningPathList.v1_serializer_class = PDFEditorLearningPathSerializerV1
        LearningPathDetail.v1_serializer_class = PDFEditorLearningPathSerializerV1

        # signals
        from django.db.models.signals import post_save
        from issuer.models import BadgeInstance
        from .signals import handle_badgeinstance_save
        post_save.connect(handle_badgeinstance_save, sender=BadgeInstance)

        # add application urls
        from mainsite.urls import urlpatterns
        from .urls import urlpatterns as pdfeditor_urls

        urlpatterns.insert(0, re_path(r"^v1/earner/badges/pdf/(?P<slug>[^/]+)$", pdfeditor_backpack_pdf, name="generate-pdf"))

        urlpatterns += pdfeditor_urls
