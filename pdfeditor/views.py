import json

from django.conf import settings
from django.http import Http404, HttpResponse, HttpResponseNotFound
from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt
from lti_tool.views import csrf_exempt
from rest_framework.authentication import (
    BasicAuthentication,
    SessionAuthentication,
    TokenAuthentication,
)
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiResponse,
)
from drf_spectacular.types import OpenApiTypes

from issuer.models import BadgeClass, BadgeInstance, Issuer
from mainsite.badge_pdf import BadgePDFCreator
from .badge_pdf import TemplateBadgePDFCreator
from .models import PDFEditorIframeUrl


@extend_schema(
    summary="Download Badge PDF",
    description=(
        "Returns a PDF version of a badge instance. "
        "The user must be the badge recipient or issuer owner."
    ),
    parameters=[
        OpenApiParameter(
            name="slug",
            type=str,
            location=OpenApiParameter.PATH,
            description="Entity ID of the badge instance.",
        ),
    ],
    responses={
        200: OpenApiResponse(
            description="PDF file",
            response=OpenApiTypes.BINARY,
        ),
        404: OpenApiResponse(description="Badge not found"),
        403: OpenApiResponse(description="Permission denied"),
    },
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([])
def pdfeditor_backpack_pdf(request, *args, **kwargs):
    slug = kwargs["slug"]
    try:
        badgeinstance = BadgeInstance.objects.get(entity_id=slug)
    except BadgeInstance.DoesNotExist:
        raise Http404
    try:
        badgeclass = BadgeClass.objects.get(
            entity_id=badgeinstance.badgeclass.entity_id
        )
    except BadgeClass.DoesNotExist:
        raise Http404

    if hasattr(badgeinstance, "pdfeditorbadgeinstance") and badgeinstance.pdfeditorbadgeinstance.pdftemplate is not None:
        pdf_creator = TemplateBadgePDFCreator(badgeinstance, badgeclass, origin=request.META.get("HTTP_ORIGIN"))
        pdf_content = pdf_creator.generate_pdf()
    else:
        pdf_creator = BadgePDFCreator()
        pdf_content = pdf_creator.generate_pdf(
            badgeinstance, badgeclass, origin=request.META.get("HTTP_ORIGIN")
        )

    return HttpResponse(pdf_content, content_type="application/pdf")


@xframe_options_exempt
@csrf_exempt
def iframe(request, *args, **kwargs):
    iframe_uuid = kwargs.get("iframe_uuid")
    try:
        iframe = PDFEditorIframeUrl.objects.get(id=iframe_uuid)
        iframe.delete()
    except PDFEditorIframeUrl.DoesNotExist:
        return HttpResponseNotFound()

    try:
        if iframe.name == "pdftemplates":
            try:
                issuer = iframe.params["issuer"]
            except KeyError:
                issuer = None

            return iframe_pdftemplates(
                request,
                iframe.params["token"],
                issuer,
                iframe.params["language"],
            )
    except Exception as e:
        if settings.DEBUG:
            raise e
        pass

    return HttpResponseNotFound()


def iframe_pdftemplates(
    request,
    token: str,
    issuer: Issuer | None,
    language: str,
):
    issuer_json = json.dumps(issuer, ensure_ascii=False)

    return render(
        request,
        "iframes/pdftemplates.html",
        context={
            "asset_path": settings.WEBCOMPONENTS_ASSETS_PATH,
            "language": language,
            "token": token,
            "issuer": issuer_json,
        }
    )
