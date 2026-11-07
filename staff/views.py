from datetime import datetime
from io import BytesIO, StringIO
from zipfile import ZIP_DEFLATED, ZipFile

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.management import call_command
from django.conf import settings
from django.db import transaction
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AccessRequestForm, AssignmentProgressForm, AttendanceMarkForm, LeaveRequestForm,
    OwnerTemporaryPasswordForm, PasswordRecoveryRequestForm, StaffPasswordChangeForm,
    PayrollForm, PayrollPaymentForm, PerformanceForm, ShiftSettingForm,
    StaffAuthenticationForm, StaffCreateForm, StaffUpdateForm, WorkAssignmentForm,
)
from .models import (
    AppSetting, AttendanceRecord, AuditEvent, LeaveRequest, PayrollRecord,
    PasswordResetRequest, PerformanceFeedback, StaffUser, WorkAssignment,
)


def roles_required(*roles):
    def decorate(view):
        @login_required
        def wrapped(request, *args, **kwargs):
            if request.user.role not in roles:
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def audit(request, action, obj=None, summary=""):
    AuditEvent.objects.create(actor=request.user, action=action,
                              object_type=obj.__class__.__name__ if obj else "",
                              object_id=str(obj.pk) if obj else "", summary=summary)


class CRMLoginView(auth_views.LoginView):
    template_name = "ars_crm/login.html"
    authentication_form = StaffAuthenticationForm
    redirect_authenticated_user = True
    next_page = reverse_lazy("dashboard")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["request_form"] = AccessRequestForm()
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        self.request.session.set_expiry(60 * 60 * 24 * 14 if self.request.POST.get("remember") == "1" else 0)
        return response


def request_access(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = AccessRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Your access request has been sent to the owner for approval.")
        return redirect("login")
    return render(request, "ars_crm/request_access.html", {"form": form})


def password_recovery_request(request):
    form = PasswordRecoveryRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            user = StaffUser.objects.select_for_update().filter(email__iexact=form.cleaned_data["email"], is_active=True).first()
            if user:
                _, created = PasswordResetRequest.objects.get_or_create(
                    user=user, status=PasswordResetRequest.Status.PENDING,
                )
            else:
                created = False
        if user and created:
            owners = list(StaffUser.objects.filter(role=StaffUser.Role.OWNER, is_active=True).values_list("email", flat=True))
            if owners:
                send_mail(
                    "ARS Garments password reset request",
                    f"{user.get_full_name()} ({user.email}) requested help resetting their password. Review the request in Access & Roles.",
                    settings.DEFAULT_FROM_EMAIL,
                    owners,
                    fail_silently=True,
                )
        return redirect("password_reset_done")
    return render(request, "ars_crm/password_reset.html", {"form": form})


@login_required
def password_change(request):
    form = StaffPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        user.must_change_password = False
        user.save(update_fields=("must_change_password",))
        update_session_auth_hash(request, user)
        audit(request, "Password changed", summary="The signed-in user changed their password.")
        messages.success(request, "Your password has been changed.")
        return redirect("dashboard")
    return render(request, "ars_crm/password_change.html", {"form": form, "active_nav": "profile"})


@login_required
def dashboard(request):
    today = timezone.localdate()
    staff_scope = StaffUser.objects.filter(is_active=True)
    attendance = AttendanceRecord.objects.filter(work_date=today)
    assignments = WorkAssignment.objects.all()
    if request.user.role == StaffUser.Role.STAFF:
        assignments = assignments.filter(assignees=request.user).distinct()
        attendance = attendance.filter(user=request.user)
        staff_scope = staff_scope.filter(pk=request.user.pk)
    context = {
        "today": today, "active_nav": "dashboard", "staff_count": staff_scope.count(),
        "present_count": attendance.filter(status__in=("present", "late")).count(),
        "on_leave_count": LeaveRequest.objects.filter(status="approved", start_date__lte=today, end_date__gte=today).count(),
        "open_assignments": assignments.exclude(status__in=("completed", "canceled")).count(),
        "overdue_assignments": sum(a.is_overdue for a in assignments),
        "assignments": assignments.prefetch_related("assignees")[:6],
        "recent_activity": AuditEvent.objects.select_related("actor")[:8] if request.user.role != "staff" else [],
        "my_attendance": AttendanceRecord.objects.filter(user=request.user).order_by("-work_date")[:5],
    }
    return render(request, "ars_crm/dashboard.html", context)


@roles_required("owner", "manager")
def staff_list(request):
    qs = StaffUser.objects.all()
    query = request.GET.get("q", "").strip()
    department = request.GET.get("department", "")
    if query:
        qs = qs.filter(Q(first_name__icontains=query) | Q(last_name__icontains=query) | Q(email__icontains=query) | Q(employee_id__icontains=query))
    if department:
        qs = qs.filter(department=department)
    return render(request, "ars_crm/staff_list.html", {"staff_members": qs, "query": query, "department": department, "departments": StaffUser.Department.choices, "active_nav": "staff"})


@roles_required("owner", "manager")
def staff_create(request):
    form = StaffCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        if request.user.role == "manager":
            member.role = StaffUser.Role.STAFF
        member.save()
        audit(request, "Staff created", member, f"Created staff account for {member.get_full_name()}.")
        messages.success(request, "Staff account created.")
        return redirect("staff_profile", pk=member.pk)
    return render(request, "ars_crm/form_page.html", {"form": form, "title": "Add staff member", "active_nav": "staff"})


@login_required
def staff_profile(request, pk):
    member = get_object_or_404(StaffUser, pk=pk)
    if request.user.role == "staff" and request.user.pk != member.pk:
        raise PermissionDenied
    return render(request, "ars_crm/staff_profile.html", {"member": member, "attendance": member.attendance_records.all()[:8], "assignments": member.assignments.all()[:8], "active_nav": "staff"})


@login_required
def staff_edit(request, pk):
    if request.user.role not in (StaffUser.Role.OWNER, StaffUser.Role.MANAGER):
        raise PermissionDenied
    member = get_object_or_404(StaffUser, pk=pk)
    previous_role = member.role
    owner_can_change_role = request.user.role == StaffUser.Role.OWNER
    form = StaffUpdateForm(request.POST or None, instance=member, allow_role=owner_can_change_role)
    if request.method == "POST" and form.is_valid():
        member = form.save(commit=False)
        if owner_can_change_role and member.role != previous_role:
            member.is_staff = member.role == StaffUser.Role.OWNER
            if member.role != StaffUser.Role.OWNER:
                member.is_superuser = False
        member.save()
        form.save_m2m()
        summary = f"Updated profile for {member.get_full_name()}."
        if owner_can_change_role and member.role != previous_role:
            summary += f" Role changed from {previous_role} to {member.role}."
        audit(request, "Staff updated", member, summary)
        messages.success(request, "Staff profile updated.")
        return redirect("staff_profile", pk=pk)
    return render(request, "ars_crm/form_page.html", {"form": form, "title": "Edit staff member", "active_nav": "staff"})


@login_required
def attendance(request):
    today = timezone.localdate()
    self_service = request.user.role in (StaffUser.Role.STAFF, StaffUser.Role.MANAGER)
    mine = request.user.role == StaffUser.Role.STAFF
    qs = AttendanceRecord.objects.select_related("user")
    if mine:
        qs = qs.filter(user=request.user)
    self_action = request.POST.get("action") if request.method == "POST" else ""
    if request.method == "POST" and self_service and self_action in ("check_in", "check_out"):
        record, _ = AttendanceRecord.objects.get_or_create(user=request.user, work_date=today)
        action = request.POST.get("action")
        now = timezone.localtime().time().replace(second=0, microsecond=0)
        if action == "check_in" and not record.check_in:
            record.check_in = now
            shift = AppSetting.objects.filter(key="shift_start").values_list("value", flat=True).first() or "09:00"
            record.status = "late" if now > datetime.strptime(shift, "%H:%M").time() else "present"
            record.save()
            audit(request, "Checked in", record, "Staff member checked in.")
            messages.success(request, "Check-in recorded.")
        elif action == "check_out" and record.check_in and not record.check_out:
            record.check_out = now
            record.save()
            audit(request, "Checked out", record, "Staff member checked out.")
            messages.success(request, "Check-out recorded.")
        else:
            messages.warning(request, "That attendance action is unavailable right now.")
        return redirect("attendance")
    can_record_attendance = request.user.role in (StaffUser.Role.OWNER, StaffUser.Role.MANAGER)
    mark_form = AttendanceMarkForm(request.POST or None, initial={"work_date": today}) if can_record_attendance else None
    if request.method == "POST" and mark_form is not None and mark_form.is_valid():
        user_id = request.POST.get("user_id")
        person = get_object_or_404(StaffUser, pk=user_id, is_active=True)
        if request.user.role == StaffUser.Role.MANAGER and person.pk == request.user.pk:
            raise PermissionDenied
        values = mark_form.cleaned_data.copy()
        work_date = values.pop("work_date")
        if request.user.role == StaffUser.Role.MANAGER:
            record, created = AttendanceRecord.objects.get_or_create(
                user=person, work_date=work_date, defaults=values
            )
            if not created:
                messages.error(request, "Attendance is already recorded for this staff member today. Only the owner can change it.")
                return redirect("attendance")
        else:
            record, _ = AttendanceRecord.objects.update_or_create(
                user=person, work_date=work_date, defaults=values
            )
        audit(request, "Attendance updated", record, f"Attendance updated for {record.user.get_full_name()}.")
        messages.success(request, "Attendance saved.")
        return redirect("attendance")
    today_records = AttendanceRecord.objects.filter(work_date=today)
    if mine:
        today_records = today_records.filter(user=request.user)
    summary = {
        "present": today_records.filter(status="present").count(),
        "late": today_records.filter(status="late").count(),
        "absent": today_records.filter(status="absent").count(),
        "on_leave": LeaveRequest.objects.filter(status="approved", start_date__lte=today, end_date__gte=today, **({"user": request.user} if mine else {})).count(),
        "checked_out": today_records.exclude(check_out__isnull=True).count(),
    }
    detail_key = request.GET.get("detail", "")
    detail_titles = {
        "present": "Present today", "late": "Late today", "absent": "Marked absent today",
        "on_leave": "On approved leave today", "checked_out": "Checked out today",
    }
    detail_records = None
    leave_detail = None
    if detail_key in detail_titles:
        if detail_key == "on_leave":
            leave_detail = LeaveRequest.objects.filter(
                status="approved", start_date__lte=today, end_date__gte=today
            ).select_related("user", "reviewed_by")
            if mine:
                leave_detail = leave_detail.filter(user=request.user)
        else:
            detail_records = AttendanceRecord.objects.filter(work_date=today).select_related("user")
            if mine:
                detail_records = detail_records.filter(user=request.user)
            if detail_key == "checked_out":
                detail_records = detail_records.exclude(check_out__isnull=True)
            else:
                detail_records = detail_records.filter(status=detail_key)
    staff_members = StaffUser.objects.filter(is_active=True)
    if request.user.role == StaffUser.Role.MANAGER:
        staff_members = staff_members.exclude(pk=request.user.pk)
    return render(request, "ars_crm/attendance.html", {"records": qs[:150], "today": today, "today_record": AttendanceRecord.objects.filter(user=request.user, work_date=today).first(), "mark_form": mark_form, "staff_members": staff_members, "attendance_summary": summary, "detail_key": detail_key if detail_key in detail_titles else "", "detail_title": detail_titles.get(detail_key), "detail_records": detail_records, "leave_detail": leave_detail, "self_service": self_service, "manager_entry_only": request.user.role == StaffUser.Role.MANAGER, "active_nav": "attendance"})


@login_required
def leave_requests(request):
    manager = request.user.role in ("owner", "manager")
    qs = LeaveRequest.objects.select_related("user", "reviewed_by")
    if not manager:
        qs = qs.filter(user=request.user)
    form = LeaveRequestForm(request.POST or None)
    if request.method == "POST" and not manager and form.is_valid():
        item = form.save(commit=False)
        item.user = request.user
        item.full_clean()
        item.save()
        audit(request, "Leave requested", item, "A leave request was submitted.")
        messages.success(request, "Leave request submitted for review.")
        return redirect("leave_requests")
    return render(request, "ars_crm/leave.html", {"requests": qs, "form": form if not manager else None, "active_nav": "attendance"})


@roles_required("owner", "manager")
@require_POST
def review_leave(request, pk):
    item = get_object_or_404(LeaveRequest, pk=pk, status="pending")
    decision = request.POST.get("decision")
    if decision not in ("approved", "rejected"):
        messages.error(request, "Choose approve or reject.")
    else:
        item.status, item.reviewed_by, item.reviewed_at = decision, request.user, timezone.now()
        item.save()
        audit(request, f"Leave {decision}", item, f"Leave request {decision} for {item.user.get_full_name()}.")
        messages.success(request, f"Leave request {decision}.")
    return redirect("leave_requests")


@login_required
def assignments(request):
    manager = request.user.role in ("owner", "manager")
    qs = WorkAssignment.objects.prefetch_related("assignees")
    if not manager:
        qs = qs.filter(assignees=request.user).distinct()
    form = WorkAssignmentForm(request.POST or None) if manager else None
    if request.method == "POST" and manager and form.is_valid():
        item = form.save(commit=False)
        item.created_by = request.user
        item.save()
        form.save_m2m()
        audit(request, "Assignment created", item, f"Created assignment: {item.title}.")
        messages.success(request, "Assignment created.")
        return redirect("assignments")
    return render(request, "ars_crm/assignments.html", {"assignments": qs, "form": form, "active_nav": "assignments"})


@login_required
@require_POST
def assignment_progress(request, pk):
    item = get_object_or_404(WorkAssignment.objects.prefetch_related("assignees"), pk=pk)
    if item.status == WorkAssignment.Status.CANCELED:
        messages.error(request, "Canceled assignments cannot be updated.")
        return redirect("assignments")
    if request.user.role == "staff" and not item.assignees.filter(pk=request.user.pk).exists():
        raise PermissionDenied
    form = AssignmentProgressForm(request.POST)
    if form.is_valid() and form.cleaned_data["completed_quantity"] <= item.total_quantity:
        item.completed_quantity = form.cleaned_data["completed_quantity"]
        item.status = form.cleaned_data["status"]
        item.save()
        audit(request, "Assignment progress updated", item, f"Updated progress on {item.title}.")
        messages.success(request, "Work progress updated.")
    else:
        messages.error(request, "Progress is invalid or exceeds the assignment quantity.")
    return redirect("assignments")


@roles_required("owner", "manager")
@require_POST
def assignment_cancel(request, pk):
    item = get_object_or_404(WorkAssignment, pk=pk)
    if item.status in (WorkAssignment.Status.COMPLETED, WorkAssignment.Status.CANCELED):
        messages.warning(request, "Completed or already canceled work cannot be canceled again.")
    else:
        item.status = WorkAssignment.Status.CANCELED
        item.save(update_fields=("status", "updated_at"))
        audit(request, "Assignment canceled", item, f"Canceled assignment: {item.title}.")
        messages.success(request, "Assignment canceled.")
    return redirect("assignments")


@roles_required("owner")
def payroll(request):
    form = PayrollForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        item = form.save()
        audit(request, "Payroll saved", item, f"Payroll saved for {item.user.get_full_name()} ({item.pay_month:%B %Y}).")
        messages.success(request, "Payroll record saved.")
        return redirect("payroll")
    return render(request, "ars_crm/payroll.html", {"records": PayrollRecord.objects.select_related("user").prefetch_related("payments"), "form": form, "active_nav": "payroll"})


@login_required
def payroll_slip(request, pk):
    item = get_object_or_404(PayrollRecord.objects.select_related("user").prefetch_related("payments"), pk=pk)
    if request.user.role != "owner" and item.user_id != request.user.pk:
        raise PermissionDenied
    return render(request, "ars_crm/payroll_slip.html", {"record": item, "active_nav": "payroll"})


@roles_required("owner")
@require_POST
def payroll_payment(request, pk):
    item = get_object_or_404(PayrollRecord, pk=pk)
    form = PayrollPaymentForm(request.POST)
    if form.is_valid():
        payment = form.save(commit=False)
        payment.payroll = item
        payment.recorded_by = request.user
        payment.save()
        paid = item.payments.aggregate(total=Sum("amount"))["total"] or 0
        if paid >= item.net_pay:
            item.status, item.paid_at = "paid", timezone.now()
            item.save(update_fields=("status", "paid_at"))
        audit(request, "Payroll payment recorded", item, f"Recorded payroll payment of INR {payment.amount}.")
        messages.success(request, "Payment recorded.")
    else:
        messages.error(request, "Enter a valid payment amount.")
    return redirect("payroll")


@login_required
def performance(request):
    manager = request.user.role in ("owner", "manager")
    qs = PerformanceFeedback.objects.select_related("user", "author")
    if not manager:
        qs = qs.filter(user=request.user)
    form = PerformanceForm(request.POST or None) if manager else None
    if request.method == "POST" and manager and form.is_valid():
        item = form.save(commit=False)
        item.author = request.user
        item.save()
        audit(request, "Performance recorded", item, f"Performance recorded for {item.user.get_full_name()}.")
        messages.success(request, "Performance entry saved.")
        return redirect("performance")
    return render(request, "ars_crm/performance.html", {"entries": qs, "form": form, "active_nav": "performance"})


@roles_required("owner")
def access_roles(request):
    if request.method == "POST":
        action = request.POST.get("action")
        if action in ("set_temporary_password", "deny_password_request"):
            reset_request = get_object_or_404(
                PasswordResetRequest.objects.select_related("user"),
                pk=request.POST.get("request_id"), status=PasswordResetRequest.Status.PENDING,
            )
            if action == "deny_password_request":
                reset_request.status = PasswordResetRequest.Status.DENIED
                reset_request.reviewed_by = request.user
                reset_request.reviewed_at = timezone.now()
                reset_request.save(update_fields=("status", "reviewed_by", "reviewed_at"))
                audit(request, "Password reset request denied", reset_request, f"Denied password reset request for {reset_request.user.get_full_name()}.")
                messages.success(request, "Password reset request denied.")
                return redirect("access_roles")

            reset_form = OwnerTemporaryPasswordForm(request.POST, user=reset_request.user)
            if reset_request.user.is_active and reset_form.is_valid():
                with transaction.atomic():
                    target = StaffUser.objects.select_for_update().get(pk=reset_request.user_id)
                    target.set_password(reset_form.cleaned_data["temporary_password"])
                    target.must_change_password = True
                    target.save(update_fields=("password", "must_change_password"))
                    reset_request.status = PasswordResetRequest.Status.RESOLVED
                    reset_request.reviewed_by = request.user
                    reset_request.reviewed_at = timezone.now()
                    reset_request.save(update_fields=("status", "reviewed_by", "reviewed_at"))
                audit(request, "Temporary password issued", reset_request, f"Issued a temporary password for {reset_request.user.get_full_name()}.")
                messages.success(request, "Temporary password set. Share it with the staff member through a secure channel.")
                return redirect("access_roles")

            if not reset_request.user.is_active:
                messages.error(request, "This account is inactive. Activate it before setting a temporary password.")
                return redirect("access_roles")
            return render(request, "ars_crm/access_roles.html", _access_roles_context(
                password_request_form=reset_form,
                active_password_request_id=reset_request.pk,
            ))

        member = get_object_or_404(StaffUser, pk=request.POST.get("user_id"))
        role, active = request.POST.get("role"), request.POST.get("is_active") == "1"
        temporary_password = request.POST.get("temporary_password", "")
        must_change_password = False
        if role not in dict(StaffUser.Role.choices):
            messages.error(request, "Select a valid role.")
        elif member.pk == request.user.pk and (not active or role != "owner"):
            messages.error(request, "You cannot remove your own owner access.")
        else:
            if active and not member.has_usable_password():
                activation_form = OwnerTemporaryPasswordForm(request.POST, user=member)
                if not activation_form.is_valid():
                    messages.error(request, "Set and confirm a valid temporary password before activating this account: " + "; ".join(activation_form.errors.get("temporary_password", []) + activation_form.errors.get("confirm_password", [])))
                    return redirect("access_roles")
                temporary_password = activation_form.cleaned_data["temporary_password"]
                must_change_password = True
            member.role, member.is_active = role, active
            member.is_staff = role == "owner"
            if active and not member.has_usable_password():
                member.set_password(temporary_password)
                member.must_change_password = must_change_password
            if role != "owner":
                member.is_superuser = False
            member.save()
            audit(request, "Access updated", member, f"Access updated for {member.get_full_name()}.")
            messages.success(request, "Account access updated.")
        return redirect("access_roles")
    return render(request, "ars_crm/access_roles.html", _access_roles_context())


def _access_roles_context(**extra):
    context = {
        "staff_members": StaffUser.objects.all(),
        "roles": StaffUser.Role.choices,
        "pending": StaffUser.objects.filter(is_active=False),
        "password_reset_requests": PasswordResetRequest.objects.filter(status=PasswordResetRequest.Status.PENDING).select_related("user"),
        "active_nav": "access",
    }
    context.update(extra)
    return context


@login_required
def my_payroll(request):
    records = PayrollRecord.objects.filter(user=request.user).prefetch_related("payments")
    return render(request, "ars_crm/my_payroll.html", {"records": records, "active_nav": "payroll"})


@roles_required("owner")
def settings_page(request):
    current = AppSetting.objects.filter(key="shift_start").values_list("value", flat=True).first() or "09:00"
    initial = {"shift_start": datetime.strptime(current, "%H:%M").time()}
    form = ShiftSettingForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save(request.user)
        audit(request, "Settings updated", summary="Updated shift start time.")
        messages.success(request, "Settings saved.")
        return redirect("settings")
    return render(request, "ars_crm/settings.html", {"form": form, "active_nav": "settings"})


@roles_required("owner")
def download_backup(request):
    output = StringIO()
    call_command("dumpdata", "--natural-foreign", "--natural-primary", "--indent", "2", stdout=output)
    today = timezone.localdate().isoformat()
    archive = BytesIO()
    with ZipFile(archive, "w", ZIP_DEFLATED) as backup_file:
        backup_file.writestr("data.json", output.getvalue())
        for staff_member in StaffUser.objects.exclude(photo="").only("photo"):
            try:
                with staff_member.photo.open("rb") as photo_file:
                    backup_file.writestr(f"media/{staff_member.photo.name}", photo_file.read())
            except (FileNotFoundError, OSError, NotImplementedError):
                continue
    response = HttpResponse(archive.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="ars-garments-backup-{today}.zip"'
    response["X-Content-Type-Options"] = "nosniff"
    audit(request, "Data backup downloaded", summary=f"Downloaded full application data backup for {today}.")
    return response
