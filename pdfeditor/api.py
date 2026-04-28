from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.utils import timezone
from oauth2_provider.models import AccessToken, Application
from oauthlib.oauth2.rfc6749.tokens import random_token_generator
from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
)
from drf_spectacular.types import OpenApiTypes
from celery import shared_task
from django.contrib.auth import get_user_model
from entity.api import (
    BaseEntityDetailView,
    BaseEntityListView,
    UncachedPaginatedViewMixin,
    VersionedObjectMixin,
)
from issuer.models import Issuer, BadgeClass
from issuer.permissions import (
    BadgrOAuthTokenHasEntityScope,
    BadgrOAuthTokenHasScope,
    IsEditor,
    IsStaff,
)
from issuer.api_v3 import RequestIframe
from issuer.serializers_v3 import RequestIframeIssuerSerializer
from mainsite.permissions import AuthenticatedWithVerifiedIdentifier, IsServerAdmin
from .permissions import (
    MayIssuePDFTemplate,
    is_pdftemplate_editor,
)
from .serializers_v1 import PDFTemplateSerializerV1, PDFEditorBadgeInstanceSerializerV1
from .models import PDFTemplate, PDFEditorIframeUrl

class IssuerPDFTemplateList(
    UncachedPaginatedViewMixin, VersionedObjectMixin, BaseEntityListView
):
    """
    GET a list of pdf templates within one issuer context or
    POST to create a new pdf template within the issuer context
    """

    model = Issuer  # used by get_object()
    permission_classes = [
        IsServerAdmin
        | (AuthenticatedWithVerifiedIdentifier & IsEditor & BadgrOAuthTokenHasScope)
        | BadgrOAuthTokenHasEntityScope
    ]
    v1_serializer_class = PDFTemplateSerializerV1
    valid_scopes = ["rw:issuer", "rw:issuer:*"]

    def get_queryset(self, request=None, **kwargs):
        issuer = self.get_object(request, **kwargs)
        return PDFTemplate.objects.filter(issuer=issuer)

    def get_context_data(self, **kwargs):
        context = super(IssuerPDFTemplateList, self).get_context_data(**kwargs)
        context["issuer"] = self.get_object(self.request, **kwargs)
        return context

    @extend_schema(
        summary="Get a list of PDFTemplates for a single Issuer",
        description="Authenticated user must have owner, editor, or staff status on the Issuer",
        tags=["Issuers", "PDFTemplates"],
        parameters=[
            OpenApiParameter(
                name="num",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                description="Request pagination of results",
            ),
        ],
    )
    def get(self, request, **kwargs):
        return super(IssuerPDFTemplateList, self).get(request, **kwargs)

    @extend_schema(
        summary="Create a new PDFTemplate associated with an Issuer",
        description="Authenticated user must have owner, editor, or staff status on the Issuer",
        tags=["Issuers", "PDFTemplate"],
    )
    def post(self, request, **kwargs):
        self.get_object(request, **kwargs)  # trigger a has_object_permissions() check
        return super(IssuerPDFTemplateList, self).post(request, **kwargs)


class PDFTemplateDetail(BaseEntityDetailView):
    model = PDFTemplate
    v1_serializer_class = PDFTemplateSerializerV1
    permission_classes = (BadgrOAuthTokenHasScope, MayIssuePDFTemplate)
    valid_scopes = ["rw:issuer"]

    @extend_schema(summary="Get a single PDFTemplate", tags=["PDFTemplates"])
    def get(self, request, **kwargs):
        return super(PDFTemplateDetail, self).get(request, **kwargs)

    @extend_schema(summary="Update a single PDFTemplate", tags=["PDFTemplate"])
    def put(self, request, **kwargs):
        if not is_pdftemplate_editor(request.user, self.get_object(request, **kwargs)):
            return Response(
                {"error": "You are not authorized to update this pdf template."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super(PDFTemplateDetail, self).put(request, **kwargs)

    @extend_schema(summary="Delete a single PDFTemplate", tags=["PDFTemplate"])
    def delete(self, request, **kwargs):
        if not is_pdftemplate_editor(request.user, self.get_object(request, **kwargs)):
            return Response(
                {"error": "You are not authorized to delete this pdf template."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super(PDFTemplateDetail, self).delete(request, **kwargs)


@extend_schema(exclude=True)
class PDFTemplateEmbed(RequestIframe):
    permission_classes = [
        IsServerAdmin
        | (AuthenticatedWithVerifiedIdentifier & IsStaff & BadgrOAuthTokenHasScope)
        | BadgrOAuthTokenHasEntityScope
    ]
    valid_scopes = ["rw:issuer", "rw:issuer:*"]

    def post(self, request, **kwargs):
        if not request.user:
            return HttpResponseForbidden()

        s = RequestIframeIssuerSerializer(data=request.data)

        if not s.is_valid():
            return HttpResponseBadRequest(json.dumps(s.errors))
        language = s.validated_data.get("lang")

        try:
            given_issuer = s.validated_data.get("issuer")
            issuers = Issuer.objects.filter(staff__id=request.user.id).distinct()
            if (
                issuers.count() == 0
                or issuers.filter(entity_id=given_issuer).count() == 0
            ):
                return HttpResponseForbidden()
            issuer = issuers.get(entity_id=given_issuer)
        except AttributeError:
            issuer = None

        if request.auth:
            application = request.auth.application
        else:
            # use public oauth app if not token auth
            application = Application.objects.get(client_type="public")

        # create short-lived oauth2 access token
        token = AccessToken.objects.create(
            user=request.user,
            application=application,
            token=random_token_generator(request, False),
            scope="rw:issuer rw:profile",
            expires=(timezone.now() + timezone.timedelta(0, 3600)),
        )

        iframe = PDFEditorIframeUrl.objects.create(
            name="pdftemplates",
            params={
                "language": language,
                "token": token.token,
                "issuer": issuer.get_json() if issuer else None,
            },
            created_by=request.user,
        )

        return JsonResponse({"url": iframe.url})


def pdfeditor_process_batch_assertions(
    self,
    assertions,
    user_id,
    badgeclass_id,
    issuerSlug,
    create_notification=False,
):
    try:
        User = get_user_model()
        user = User.objects.get(id=user_id)
        badgeclass = BadgeClass.objects.get(id=badgeclass_id)

        total = len(assertions)

        processed = 0
        successful = []
        errors = []

        for assertion in assertions:
            request_entity_id = assertion.get("request_entity_id")
            assertion["create_notification"] = create_notification

            serializer = PDFEditorBadgeInstanceSerializerV1(
                data=assertion,
                context={
                    "badgeclass": badgeclass,
                    "user": user,
                    "issuerSlug": issuerSlug,
                },
            )

            if serializer.is_valid():
                try:
                    instance = serializer.save(created_by=user)
                    successful.append(
                        {
                            "badge_instance": PDFEditorBadgeInstanceSerializerV1(instance).data,
                            "request_entity_id": request_entity_id,
                        }
                    )
                except Exception as e:
                    errors.append({"assertion": assertion, "error": str(e)})
            else:
                errors.append({"assertion": assertion, "error": serializer.errors})

            processed += 1

            # Emit progress after each iteration
            self.update_state(
                state="PROGRESS",
                meta={
                    "processed": processed,
                    "total": total,
                    "data": successful,
                    "errors": errors,
                },
            )

        return {
            "success": len(errors) == 0,
            "status": status.HTTP_201_CREATED
            if len(errors) == 0
            else status.HTTP_207_MULTI_STATUS,
            "data": successful,
            "errors": errors,
        }

    except Exception as e:
        return {
            "success": False,
            "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
            "error": str(e),
        }
