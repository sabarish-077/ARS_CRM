from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    AppSetting, AttendanceRecord, LeaveRequest, PayrollPayment, PayrollRecord,
    PerformanceFeedback, StaffUser, WorkAssignment,
)


class StaffAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label="Work email", widget=forms.EmailInput(attrs={"autocomplete": "username", "placeholder": "you@arsgarments.com"}))
    password = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password", "placeholder": "Enter your password"}))


class AccessRequestForm(forms.Form):
    first_name = forms.CharField(max_length=160, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Your full name"}))
    email = forms.EmailField(label="Work email", widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@arsgarments.com"}))
    department = forms.ChoiceField(label="Department", choices=StaffUser.Department.choices)
    job_title = forms.CharField(max_length=100, label="Job title", widget=forms.TextInput(attrs={"placeholder": "e.g. Tailor, Cutter, Packer"}))

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if StaffUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account already exists or is awaiting approval for this email.")
        return email

    def save(self):
        names = self.cleaned_data["first_name"].strip().split(maxsplit=1)
        return StaffUser.objects.create_user(email=self.cleaned_data["email"], first_name=names[0], last_name=names[1] if len(names) > 1 else "", department=self.cleaned_data["department"], job_title=self.cleaned_data["job_title"].strip(), is_active=False)


class StaffCreateForm(forms.ModelForm):
    password = forms.CharField(min_length=10, label="Temporary password", widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=((StaffUser.Role.MANAGER, "Manager"), (StaffUser.Role.STAFF, "Staff")))

    class Meta:
        model = StaffUser
        fields = ("employee_id", "first_name", "last_name", "email", "phone", "address", "job_title", "department", "joined_on", "employment_status", "role")
        widgets = {"joined_on": forms.DateInput(attrs={"type": "date"})}

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if StaffUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with this email already exists.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        user.must_change_password = True
        user.is_active = True
        user.is_staff = user.role == StaffUser.Role.OWNER
        if commit:
            user.save()
        return user


class StaffUpdateForm(forms.ModelForm):
    class Meta:
        model = StaffUser
        fields = ("employee_id", "first_name", "last_name", "email", "phone", "address", "job_title", "department", "joined_on", "employment_status", "role")
        widgets = {"joined_on": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, allow_role=False, **kwargs):
        super().__init__(*args, **kwargs)
        if not allow_role:
            self.fields.pop("role")


class AttendanceMarkForm(forms.ModelForm):
    class Meta:
        model = AttendanceRecord
        fields = ("work_date", "check_in", "check_out", "status", "note")
        widgets = {"work_date": forms.DateInput(attrs={"type": "date"}), "check_in": forms.TimeInput(attrs={"type": "time"}), "check_out": forms.TimeInput(attrs={"type": "time"})}

    def clean_work_date(self):
        work_date = self.cleaned_data["work_date"]
        if work_date != timezone.localdate():
            raise ValidationError("Attendance can only be managed for today.")
        return work_date


class LeaveRequestForm(forms.ModelForm):
    class Meta:
        model = LeaveRequest
        fields = ("start_date", "end_date", "reason")
        widgets = {"start_date": forms.DateInput(attrs={"type": "date"}), "end_date": forms.DateInput(attrs={"type": "date"}), "reason": forms.Textarea(attrs={"rows": 3})}


class WorkAssignmentForm(forms.ModelForm):
    class Meta:
        model = WorkAssignment
        fields = ("title", "order_reference", "description", "total_quantity", "completed_quantity", "assignees", "due_date", "status", "priority", "notes")
        widgets = {"due_date": forms.DateInput(attrs={"type": "date"}), "description": forms.Textarea(attrs={"rows": 3}), "notes": forms.Textarea(attrs={"rows": 2}), "assignees": forms.SelectMultiple(attrs={"size": 5})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assignees"].queryset = StaffUser.objects.filter(is_active=True).order_by("first_name", "last_name")
        self.fields["status"].choices = [(key, label) for key, label in WorkAssignment.Status.choices if key != WorkAssignment.Status.CANCELED]

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("completed_quantity", 0) > cleaned.get("total_quantity", 0):
            self.add_error("completed_quantity", "Completed quantity cannot exceed the total quantity.")
        return cleaned


class AssignmentProgressForm(forms.Form):
    status = forms.ChoiceField(choices=WorkAssignment.Status.choices)
    completed_quantity = forms.IntegerField(min_value=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["status"].choices = [(key, label) for key, label in WorkAssignment.Status.choices if key != WorkAssignment.Status.CANCELED]


class PayrollForm(forms.ModelForm):
    class Meta:
        model = PayrollRecord
        fields = ("user", "pay_month", "base_salary", "days_worked", "advances", "deductions", "status", "note")
        widgets = {"pay_month": forms.DateInput(attrs={"type": "date"}), "base_salary": forms.NumberInput(attrs={"step": "0.01"}), "advances": forms.NumberInput(attrs={"step": "0.01"}), "deductions": forms.NumberInput(attrs={"step": "0.01"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = StaffUser.objects.filter(is_active=True).order_by("first_name", "last_name")

    def clean_pay_month(self):
        return self.cleaned_data["pay_month"].replace(day=1)

    def clean(self):
        cleaned = super().clean()
        base = cleaned.get("base_salary")
        advances = cleaned.get("advances") or 0
        deductions = cleaned.get("deductions") or 0
        if base is not None and base - advances - deductions < 0:
            self.add_error("deductions", "Advances and deductions cannot exceed the base salary.")
        return cleaned


class PayrollPaymentForm(forms.ModelForm):
    class Meta:
        model = PayrollPayment
        fields = ("amount", "method", "reference", "note")
        widgets = {"amount": forms.NumberInput(attrs={"step": "0.01"})}


class PerformanceForm(forms.ModelForm):
    class Meta:
        model = PerformanceFeedback
        fields = ("user", "month", "completed_quantity", "on_time_percentage", "feedback")
        widgets = {"month": forms.DateInput(attrs={"type": "date"}), "feedback": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = StaffUser.objects.filter(is_active=True).order_by("first_name", "last_name")

    def clean_month(self):
        return self.cleaned_data["month"].replace(day=1)


class ShiftSettingForm(forms.Form):
    shift_start = forms.TimeField(widget=forms.TimeInput(attrs={"type": "time"}))

    def save(self, user):
        value = self.cleaned_data["shift_start"].strftime("%H:%M")
        AppSetting.objects.update_or_create(key="shift_start", defaults={"value": value, "updated_by": user})


class PasswordRecoveryRequestForm(forms.Form):
    email = forms.EmailField(label="Work email", widget=forms.EmailInput(attrs={"autocomplete": "email"}))

    def clean_email(self):
        return self.cleaned_data["email"].strip().lower()


class StaffPasswordChangeForm(PasswordChangeForm):
    pass


class OwnerTemporaryPasswordForm(forms.Form):
    temporary_password = forms.CharField(min_length=10, label="Temporary password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))
    confirm_password = forms.CharField(label="Confirm temporary password", widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def __init__(self, *args, user, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)

    def clean_temporary_password(self):
        password = self.cleaned_data["temporary_password"]
        validate_password(password, user=self.user)
        return password

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("temporary_password") and cleaned.get("confirm_password") and cleaned["temporary_password"] != cleaned["confirm_password"]:
            self.add_error("confirm_password", "The passwords do not match.")
        return cleaned


for _form_class in (StaffCreateForm, StaffUpdateForm, AttendanceMarkForm, LeaveRequestForm,
                    WorkAssignmentForm, PayrollForm, PayrollPaymentForm, PerformanceForm,
                    ShiftSettingForm, PasswordRecoveryRequestForm, StaffPasswordChangeForm,
                    OwnerTemporaryPasswordForm):
    for _field in _form_class.base_fields.values():
        _widget = _field.widget
        if isinstance(_widget, forms.CheckboxInput):
            _widget.attrs.setdefault("class", "form-check-input")
        elif isinstance(_widget, forms.SelectMultiple):
            _widget.attrs.setdefault("class", "form-select")
        elif isinstance(_widget, forms.Select):
            _widget.attrs.setdefault("class", "form-select")
        else:
            _widget.attrs.setdefault("class", "form-control")
