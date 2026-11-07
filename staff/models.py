from decimal import Decimal

from django.contrib.auth.base_user import BaseUserManager
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone


class StaffUserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required.")
        user = self.model(email=self.normalize_email(email).strip().lower(), **extra_fields)
        user.set_password(password) if password else user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("role", StaffUser.Role.OWNER)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Owner account requires staff and superuser flags.")
        return self.create_user(email, password, **extra_fields)


class StaffUser(AbstractBaseUser, PermissionsMixin):
    class Role(models.TextChoices):
        OWNER = "owner", "Owner"
        MANAGER = "manager", "Manager"
        STAFF = "staff", "Staff"

    class Department(models.TextChoices):
        CUTTING = "cutting", "Cutting"
        STITCHING = "stitching", "Stitching"
        PACKING = "packing", "Packing"
        SALES = "sales", "Sales"
        ADMIN = "admin", "Admin"

    class EmploymentStatus(models.TextChoices):
        ACTIVE = "active", "Active"
        ON_LEAVE = "on_leave", "On leave"
        INACTIVE = "inactive", "Inactive"

    email = models.EmailField(unique=True)
    employee_id = models.CharField(max_length=24, unique=True, null=True, blank=True)
    first_name = models.CharField(max_length=80)
    last_name = models.CharField(max_length=80, blank=True)
    phone = models.CharField(max_length=24, blank=True)
    address = models.TextField(blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.STAFF)
    job_title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=16, choices=Department.choices, blank=True)
    joined_on = models.DateField(null=True, blank=True)
    employment_status = models.CharField(max_length=16, choices=EmploymentStatus.choices, default=EmploymentStatus.ACTIVE)
    photo = models.ImageField(upload_to="staff/photos/", blank=True)
    must_change_password = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)
    objects = StaffUserManager()
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name"]

    class Meta:
        ordering = ("first_name", "last_name", "email")
        verbose_name = "staff member"
        verbose_name_plural = "staff members"

    def __str__(self):
        return self.get_full_name() or self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_short_name(self):
        return self.first_name

    @property
    def initials(self):
        return (self.first_name[:1] + self.last_name[:1]).upper() or self.email[:1].upper()


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "present", "Present"
        LATE = "late", "Late"
        ABSENT = "absent", "Absent"
        ON_LEAVE = "on_leave", "On leave"
        HOLIDAY = "holiday", "Holiday"

    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name="attendance_records")
    work_date = models.DateField(default=timezone.localdate)
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PRESENT)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-work_date", "user__first_name")
        constraints = [models.UniqueConstraint(fields=("user", "work_date"), name="one_attendance_per_user_day")]

    @property
    def total_hours(self):
        if not self.check_in or not self.check_out:
            return Decimal("0.00")
        start = timezone.datetime.combine(self.work_date, self.check_in)
        end = timezone.datetime.combine(self.work_date, self.check_out)
        seconds = (end - start).total_seconds()
        if seconds < 0:
            seconds += 86400
        return (Decimal(str(seconds)) / Decimal("3600")).quantize(Decimal("0.01"))


class LeaveRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name="leave_requests")
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.CharField(max_length=500)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    reviewed_by = models.ForeignKey(StaffUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_leave_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date and self.start_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date must be on or after start date."})


class WorkAssignment(models.Model):
    class Status(models.TextChoices):
        ASSIGNED = "assigned", "Assigned"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        DELAYED = "delayed", "Delayed"
        CANCELED = "canceled", "Canceled"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent"

    title = models.CharField(max_length=180)
    order_reference = models.CharField(max_length=80, blank=True)
    description = models.TextField(blank=True)
    total_quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    completed_quantity = models.PositiveIntegerField(default=0)
    assignees = models.ManyToManyField(StaffUser, related_name="assignments", blank=True)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ASSIGNED)
    priority = models.CharField(max_length=12, choices=Priority.choices, default=Priority.NORMAL)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(StaffUser, null=True, on_delete=models.SET_NULL, related_name="created_assignments")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("due_date", "-created_at")

    @property
    def is_overdue(self):
        return bool(self.due_date and self.due_date < timezone.localdate() and self.status not in (self.Status.COMPLETED, self.Status.CANCELED))

    @property
    def display_status(self):
        return self.Status.DELAYED if self.is_overdue else self.status

    @property
    def progress_percent(self):
        if not self.total_quantity:
            return 0
        return min(100, round(self.completed_quantity * 100 / self.total_quantity))


class PayrollRecord(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"

    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name="payroll_records")
    pay_month = models.DateField(help_text="Use the first day of the payroll month.")
    base_salary = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    days_worked = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(31)])
    advances = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    deductions = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    note = models.CharField(max_length=500, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-pay_month", "user__first_name")
        constraints = [models.UniqueConstraint(fields=("user", "pay_month"), name="one_payroll_per_user_month")]

    @property
    def net_pay(self):
        return self.base_salary - self.advances - self.deductions


class PayrollPayment(models.Model):
    payroll = models.ForeignKey(PayrollRecord, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=40, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(StaffUser, null=True, on_delete=models.SET_NULL)

    class Meta:
        ordering = ("-paid_at",)


class PerformanceFeedback(models.Model):
    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name="performance_entries")
    month = models.DateField(help_text="Use the first day of the month.")
    completed_quantity = models.PositiveIntegerField(default=0)
    on_time_percentage = models.PositiveSmallIntegerField(default=0, validators=[MaxValueValidator(100)])
    feedback = models.TextField(blank=True)
    author = models.ForeignKey(StaffUser, null=True, on_delete=models.SET_NULL, related_name="authored_feedback")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-month", "user__first_name")
        constraints = [models.UniqueConstraint(fields=("user", "month"), name="one_performance_entry_per_user_month")]


class AppSetting(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    value = models.CharField(max_length=255)
    updated_by = models.ForeignKey(StaffUser, null=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.key}={self.value}"


class AuditEvent(models.Model):
    actor = models.ForeignKey(StaffUser, null=True, on_delete=models.SET_NULL, related_name="audit_events")
    action = models.CharField(max_length=120)
    object_type = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=80, blank=True)
    summary = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)


class PasswordResetRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        RESOLVED = "resolved", "Resolved"
        DENIED = "denied", "Denied"

    user = models.ForeignKey(StaffUser, on_delete=models.CASCADE, related_name="password_reset_requests")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_by = models.ForeignKey(StaffUser, null=True, blank=True, on_delete=models.SET_NULL, related_name="reviewed_password_reset_requests")
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Password reset request: {self.user} ({self.status})"
