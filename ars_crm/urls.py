from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.views.generic.base import RedirectView
from django.urls import path
from staff import views

urlpatterns = [
    path("favicon.ico", RedirectView.as_view(url="/static/ars_crm/favicon.svg", permanent=False), name="favicon"),
    path("admin/", admin.site.urls),
    path("", views.dashboard, name="dashboard"),
    path("login/", views.CRMLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("request-access/", views.request_access, name="request_access"),
    path("password-reset/", views.password_recovery_request, name="password_reset"),
    path("password-reset/done/", auth_views.PasswordResetDoneView.as_view(template_name="ars_crm/password_reset_done.html"), name="password_reset_done"),
    path("password-change/", views.password_change, name="password_change"),
    path("staff/", views.staff_list, name="staff_list"),
    path("staff/add/", views.staff_create, name="staff_create"),
    path("staff/<int:pk>/", views.staff_profile, name="staff_profile"),
    path("staff/<int:pk>/edit/", views.staff_edit, name="staff_edit"),
    path("attendance/", views.attendance, name="attendance"),
    path("leave/", views.leave_requests, name="leave_requests"),
    path("leave/<int:pk>/review/", views.review_leave, name="review_leave"),
    path("assignments/", views.assignments, name="assignments"),
    path("assignments/<int:pk>/progress/", views.assignment_progress, name="assignment_progress"),
    path("assignments/<int:pk>/cancel/", views.assignment_cancel, name="assignment_cancel"),
    path("payroll/", views.payroll, name="payroll"),
    path("my-pay/", views.my_payroll, name="my_payroll"),
    path("payroll/<int:pk>/slip/", views.payroll_slip, name="payroll_slip"),
    path("payroll/<int:pk>/payment/", views.payroll_payment, name="payroll_payment"),
    path("performance/", views.performance, name="performance"),
    path("access/", views.access_roles, name="access_roles"),
    path("settings/", views.settings_page, name="settings"),
    path("backup/download/", views.download_backup, name="download_backup"),
]
