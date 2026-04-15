from django.urls import re_path, path

from .api import (
    IssuerPDFTemplateList,
    PDFTemplateDetail,
    PDFTemplateEmbed,
)

from .views import iframe

urlpatterns = [
    re_path(
        r"^v1/issuer/issuers/(?P<slug>[^/]+)/pdftemplate$",
        IssuerPDFTemplateList.as_view(),
        name="v1_api_pdftemplate_list",
        kwargs={"version": "v1"}
    ),
    re_path(
        r"^v1/issuer/issuers/(?P<issuerSlug>[^/]+)/pdftemplate/(?P<slug>[^/]+)$",
        PDFTemplateDetail.as_view(),
        name="v1_api_pdftemplate_detail",
        kwargs={"version": "v1"}
    ),
    re_path(
        r"^v3/issuer/pdftemplate-embed",
        PDFTemplateEmbed.as_view(),
        name="v3_api_pdftemplate_embed",
        kwargs={"version": "v3"}
    ),
    path("pdfeditor-iframes/<uuid:iframe_uuid>/", iframe, name="pdfeditor_iframe"),
]
