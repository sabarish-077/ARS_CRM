from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import StaffUser

@admin.register(StaffUser)
class StaffUserAdmin(UserAdmin):
    model = StaffUser
    ordering = ("email",)
    list_display = ("email", "first_name", "last_name", "role", "department", "is_active")
    list_filter = ("role", "department", "employment_status", "is_active")
    search_fields = ("email", "first_name", "last_name", "employee_id")
    fieldsets = ((None, {"fields": ("email", "password")}), ("Personal details", {"fields": ("first_name", "last_name", "employee_id", "phone", "address", "photo")}), ("Work details", {"fields": ("role", "job_title", "department", "joined_on", "employment_status")}), ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}), ("Dates", {"fields": ("last_login", "date_joined")}))
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "first_name", "password1", "password2", "role", "is_active", "is_staff")}),)
    filter_horizontal = ("groups", "user_permissions")
