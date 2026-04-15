from rest_framework import permissions
import rules

from issuer.models import IssuerStaff
from issuer.permissions import _is_server_admin

@rules.predicate
def is_pdftemplate_staff(user, pdftemplate):
    return any(
        staff.user_id == user.id
        for staff in pdftemplate.cached_issuer.cached_issuerstaff()
    )


@rules.predicate
def is_pdftemplate_editor(user, pdftemplate):
    return any(
        staff.role in [IssuerStaff.ROLE_EDITOR, IssuerStaff.ROLE_OWNER]
        for staff in pdftemplate.cached_issuer.cached_issuerstaff()
        if staff.user_id == user.id
    )


@rules.predicate
def is_pdftemplate_owner(user, pdftemplate):
    return any(
        staff.role == IssuerStaff.ROLE_OWNER
        for staff in pdftemplate.cached_issuer.cached_issuerstaff()
        if staff.user_id == user.id
    )


can_issue_pdftemplate = is_pdftemplate_staff
can_edit_pdftemplate = is_pdftemplate_owner | is_pdftemplate_editor

# FIXME: should those be set here?
try:
    rules.add_perm("issuer.can_issue_pdftemplate", can_issue_pdftemplate)
    rules.add_perm("issuer.can_edit_pdftemplate", can_edit_pdftemplate)
except KeyError:
    pass


class MayIssuePDFTemplate(permissions.BasePermission):
    """
    ---
    model: PDFTemplate
    """

    def has_object_permission(self, request, view, pdftemplate):
        return _is_server_admin(request) or request.user.has_perm(
            "issuer.can_issue_pdftemplate", pdftemplate
        )
