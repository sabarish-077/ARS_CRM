from datetime import date, timedelta

from django.core.mail.backends.base import BaseEmailBackend
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import AttendanceRecord, LeaveRequest, PasswordResetRequest, PayrollRecord, StaffUser, WorkAssignment


class FailingEmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if self.fail_silently:
            return 0
        raise RuntimeError("Simulated email service failure")


class StaffPortalWorkflowTests(TestCase):
    def setUp(self):
        self.owner = StaffUser.objects.create_user("owner@ars.test", "Owner-pass-123", first_name="Owner", role="owner", is_active=True)
        self.manager = StaffUser.objects.create_user("manager@ars.test", "Manager-pass-123", first_name="Manager", role="manager", is_active=True)
        self.staff = StaffUser.objects.create_user("staff@ars.test", "Staff-pass-123", first_name="Staff", role="staff", is_active=True)
        self.other = StaffUser.objects.create_user("other@ars.test", "Other-pass-123", first_name="Other", role="staff", is_active=True)

    def test_role_protected_pages_and_self_service_slip(self):
        pay = PayrollRecord.objects.create(user=self.staff, pay_month=date.today().replace(day=1), base_salary=1000)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("payroll")).status_code, 403)
        self.assertEqual(self.client.get(reverse("access_roles")).status_code, 403)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("payroll_slip", args=[pay.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("staff_profile", args=[self.other.pk])).status_code, 403)

    def test_staff_can_check_in_and_submit_leave(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("attendance"), {"action": "check_in"})
        self.assertEqual(response.status_code, 302)
        today_record = AttendanceRecord.objects.get(user=self.staff, work_date=timezone.localdate())
        self.assertIsNotNone(today_record.check_in)
        self.client.post(reverse("attendance"), {"action": "check_in", "work_date": timezone.localdate() - timedelta(days=1)})
        self.assertEqual(AttendanceRecord.objects.filter(user=self.staff).count(), 1)
        response = self.client.post(reverse("leave_requests"), {"start_date": timezone.localdate() + timedelta(days=1), "end_date": timezone.localdate() + timedelta(days=2), "reason": "Personal"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(LeaveRequest.objects.filter(user=self.staff, status="pending").exists())

    def test_staff_can_update_only_assigned_work(self):
        work = WorkAssignment.objects.create(title="Stitch order", total_quantity=20, created_by=self.manager)
        work.assignees.add(self.staff)
        self.client.force_login(self.staff)
        response = self.client.post(reverse("assignment_progress", args=[work.pk]), {"status": "in_progress", "completed_quantity": 8})
        self.assertEqual(response.status_code, 302)
        work.refresh_from_db()
        self.assertEqual(work.completed_quantity, 8)
        work.assignees.set([self.other])
        self.assertEqual(self.client.post(reverse("assignment_progress", args=[work.pk]), {"status": "completed", "completed_quantity": 20}).status_code, 403)

    def test_manager_can_review_leave_but_cannot_edit_payroll(self):
        leave = LeaveRequest.objects.create(user=self.staff, start_date=timezone.localdate(), end_date=timezone.localdate(), reason="Personal")
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse("review_leave", args=[leave.pk]), {"decision": "approved"}).status_code, 302)
        leave.refresh_from_db()
        self.assertEqual(leave.status, "approved")
        self.assertEqual(self.client.post(reverse("payroll_payment", args=[1])).status_code, 403)

    def test_owner_activation_sets_first_password(self):
        pending = StaffUser.objects.create_user("pending@ars.test", first_name="Pending", is_active=False)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("access_roles"), {
            "user_id": pending.pk, "role": "staff", "is_active": "1",
            "temporary_password": "Temp-Onboard-Password-723!",
            "confirm_password": "Temp-Onboard-Password-723!",
        })
        self.assertEqual(response.status_code, 302)
        pending.refresh_from_db()
        self.assertTrue(pending.is_active)
        self.assertTrue(pending.check_password("Temp-Onboard-Password-723!"))
        self.assertTrue(pending.must_change_password)

    def test_manager_cannot_assign_a_higher_role_when_creating_staff(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff_create"), {
            "first_name": "New", "last_name": "Manager", "email": "new@ars.test",
            "department": "stitching", "role": "manager", "employment_status": "active",
            "password": "New-user-pass-123",
        })
        self.assertEqual(response.status_code, 302)
        created = StaffUser.objects.get(email="new@ars.test")
        self.assertEqual(created.role, "staff")

    def test_managers_can_enter_once_but_owner_only_can_edit_todays_attendance(self):
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("attendance")).status_code, 200)
        manager_entry = {"user_id": self.staff.pk, "work_date": timezone.localdate(), "status": "present", "check_in": "09:00", "check_out": "", "note": ""}
        self.assertEqual(self.client.post(reverse("attendance"), manager_entry).status_code, 302)
        self.assertEqual(self.client.post(reverse("attendance"), {**manager_entry, "status": "absent"}).status_code, 302)
        today_record = AttendanceRecord.objects.get(user=self.staff, work_date=timezone.localdate())
        self.assertEqual(today_record.status, "present")
        manager_self_entry = {**manager_entry, "user_id": self.manager.pk}
        self.assertEqual(self.client.post(reverse("attendance"), manager_self_entry).status_code, 403)
        self.assertFalse(AttendanceRecord.objects.filter(user=self.manager, work_date=timezone.localdate()).exists())
        self.assertEqual(self.client.post(reverse("attendance"), {"action": "check_in"}).status_code, 302)
        manager_record = AttendanceRecord.objects.get(user=self.manager, work_date=timezone.localdate())
        first_check_in = manager_record.check_in
        self.assertEqual(self.client.post(reverse("attendance"), {"action": "check_in"}).status_code, 302)
        manager_record.refresh_from_db()
        self.assertEqual(manager_record.check_in, first_check_in)
        self.assertEqual(self.client.post(reverse("attendance"), {"action": "check_out"}).status_code, 302)
        manager_record.refresh_from_db()
        self.assertIsNotNone(manager_record.check_out)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("attendance"), {
            "user_id": self.staff.pk, "work_date": timezone.localdate() - timedelta(days=1),
            "status": "present", "check_in": "09:00", "check_out": "17:00", "note": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.filter(user=self.staff).count(), 1)
        self.assertEqual(self.client.post(reverse("attendance"), {**manager_entry, "status": "absent"}).status_code, 302)
        self.assertEqual(self.client.post(reverse("attendance"), {**manager_entry, "status": "late"}).status_code, 302)
        today_record.refresh_from_db()
        self.assertEqual(today_record.status, "late")

    def test_attendance_summary_links_show_matching_people_and_details(self):
        today = timezone.localdate()
        AttendanceRecord.objects.create(user=self.staff, work_date=today, status="present", check_in="09:00")
        AttendanceRecord.objects.create(user=self.other, work_date=today, status="late", check_in="09:30", check_out="17:00")
        LeaveRequest.objects.create(user=self.manager, start_date=today, end_date=today, reason="Approved leave", status="approved", reviewed_by=self.owner)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("attendance"), {"detail": "late"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["detail_records"].values_list("user_id", flat=True)), [self.other.pk])
        self.assertContains(response, "Late today · View")
        leave_response = self.client.get(reverse("attendance"), {"detail": "on_leave"})
        self.assertEqual(list(leave_response.context["leave_detail"].values_list("user_id", flat=True)), [self.manager.pk])

    def test_owner_can_cancel_assignment_and_download_backup(self):
        work = WorkAssignment.objects.create(title="Pack order", total_quantity=10, created_by=self.owner)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse("assignment_cancel", args=[work.pk])).status_code, 302)
        work.refresh_from_db()
        self.assertEqual(work.status, WorkAssignment.Status.CANCELED)
        self.assertEqual(self.client.get(reverse("download_backup")).status_code, 403)
        self.client.force_login(self.owner)
        response = self.client.get(reverse("download_backup"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment; filename=\"ars-garments-backup-", response["Content-Disposition"])
        self.assertEqual(response["Content-Type"], "application/zip")

    def test_owner_can_change_staff_role_from_profile_edit(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("staff_edit", args=[self.staff.pk]), {
            "first_name": self.staff.first_name, "last_name": self.staff.last_name,
            "email": self.staff.email, "phone": self.staff.phone, "address": self.staff.address,
            "job_title": self.staff.job_title, "department": self.staff.department,
            "joined_on": "", "employment_status": self.staff.employment_status,
            "role": StaffUser.Role.MANAGER,
        })
        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.role, StaffUser.Role.MANAGER)

    def test_manager_cannot_change_role_from_profile_edit(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse("staff_edit", args=[self.staff.pk]), {
            "first_name": self.staff.first_name, "last_name": self.staff.last_name,
            "email": self.staff.email, "phone": self.staff.phone, "address": self.staff.address,
            "job_title": self.staff.job_title, "department": self.staff.department,
            "joined_on": "", "employment_status": self.staff.employment_status,
            "role": StaffUser.Role.OWNER,
        })
        self.assertEqual(response.status_code, 302)
        self.staff.refresh_from_db()
        self.assertEqual(self.staff.role, StaffUser.Role.STAFF)

    def test_staff_can_change_password_and_keep_session(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse("password_change"), {
            "old_password": "Staff-pass-123",
            "new_password1": "Stitching-Sunrise-2026!",
            "new_password2": "Stitching-Sunrise-2026!",
        })
        self.assertRedirects(response, reverse("dashboard"))
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("Stitching-Sunrise-2026!"))
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_password_change_rejects_bad_current_mismatch_and_weak_password(self):
        self.client.force_login(self.staff)
        url = reverse("password_change")
        for payload in (
            {"old_password": "wrong", "new_password1": "Stitching-Sunrise-2026!", "new_password2": "Stitching-Sunrise-2026!"},
            {"old_password": "Staff-pass-123", "new_password1": "Stitching-Sunrise-2026!", "new_password2": "Stitching-Sunrise-2026?"},
            {"old_password": "Staff-pass-123", "new_password1": "password", "new_password2": "password"},
        ):
            response = self.client.post(url, payload)
            self.assertEqual(response.status_code, 200)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.check_password("Staff-pass-123"))

    def test_temporary_password_forces_change_before_other_pages(self):
        self.staff.must_change_password = True
        self.staff.set_password("Interim-Sewing-9uL#2wP")
        self.staff.save(update_fields=("must_change_password", "password"))
        self.client.force_login(self.staff)
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, reverse("password_change"))
        response = self.client.post(reverse("password_change"), {
            "old_password": "Interim-Sewing-9uL#2wP",
            "new_password1": "New-Stitching-Password-2026!",
            "new_password2": "New-Stitching-Password-2026!",
        })
        self.assertRedirects(response, reverse("dashboard"))
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.must_change_password)
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_recovery_request_is_queued_and_owner_is_emailed(self):
        response = self.client.post(reverse("password_reset"), {"email": self.staff.email}, follow=True)
        self.assertEqual(response.status_code, 200)
        request = PasswordResetRequest.objects.get(user=self.staff, status=PasswordResetRequest.Status.PENDING)
        self.assertContains(response, "request was sent to the owner")
        from django.core import mail
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.owner.email])
        self.assertIn(self.staff.email, mail.outbox[0].body)
        self.assertNotIn("temporary password", mail.outbox[0].body.lower())
        self.client.force_login(self.owner)
        self.assertContains(self.client.get(reverse("access_roles")), self.staff.email)

    def test_unknown_and_inactive_emails_get_same_recovery_confirmation(self):
        inactive = StaffUser.objects.create_user("inactive@ars.test", first_name="Inactive", is_active=False)
        unknown = self.client.post(reverse("password_reset"), {"email": "unknown@ars.test"}, follow=True)
        inactive_response = self.client.post(reverse("password_reset"), {"email": inactive.email}, follow=True)
        self.assertEqual(unknown.content, inactive_response.content)
        self.assertFalse(PasswordResetRequest.objects.exists())

    @override_settings(EMAIL_BACKEND="staff.tests.FailingEmailBackend")
    def test_recovery_request_stays_queued_when_email_fails(self):
        response = self.client.post(reverse("password_reset"), {"email": self.staff.email}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(PasswordResetRequest.objects.filter(user=self.staff, status="pending").exists())

    def test_only_owner_can_issue_temp_password_and_staff_must_change_it(self):
        reset_request = PasswordResetRequest.objects.create(user=self.staff)
        payload = {
            "action": "set_temporary_password", "request_id": reset_request.pk,
            "temporary_password": "Interim-Sewing-9uL#2wP",
            "confirm_password": "Interim-Sewing-9uL#2wP",
        }
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(reverse("access_roles"), payload).status_code, 403)
        self.client.force_login(self.owner)
        mismatch_response = self.client.post(reverse("access_roles"), {
            **payload, "confirm_password": "Another-Temporary-Password-1!",
        })
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertContains(mismatch_response, "The passwords do not match.")
        response = self.client.post(reverse("access_roles"), payload)
        self.assertRedirects(response, reverse("access_roles"))
        self.staff.refresh_from_db()
        reset_request.refresh_from_db()
        self.assertTrue(self.staff.check_password("Interim-Sewing-9uL#2wP"))
        self.assertTrue(self.staff.must_change_password)
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.RESOLVED)
        self.client.force_login(self.staff)
        self.assertRedirects(self.client.get(reverse("assignments")), reverse("password_change"))

    def test_owner_can_deny_password_request(self):
        reset_request = PasswordResetRequest.objects.create(user=self.staff)
        self.client.force_login(self.owner)
        response = self.client.post(reverse("access_roles"), {
            "action": "deny_password_request", "request_id": reset_request.pk,
        })
        self.assertRedirects(response, reverse("access_roles"))
        reset_request.refresh_from_db()
        self.staff.refresh_from_db()
        self.assertEqual(reset_request.status, PasswordResetRequest.Status.DENIED)
        self.assertTrue(self.staff.check_password("Staff-pass-123"))
        self.assertFalse(self.staff.must_change_password)
