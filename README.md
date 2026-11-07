# ARS Garments Staff CRM

The Django app uses Django 5.2 LTS, MySQL 8, Django templates, Bootstrap 5,
vanilla JavaScript, and Bootstrap Icons. It provides the ARS Garments staff
portal, with sign-in, access requests, staff profiles, attendance and leave,
assignments and progress, payroll slips and payments, monthly performance,
role management, operational settings, and an activity dashboard.

The existing `app.py` / `index.html` prototype, if present in an earlier copy,
is separate from this Django project and is not used by `manage.py`.

## Data model

- `staff_user`: login, role, employee ID, contact/profile fields, department,
  title, start date, and employment status.
- `attendance_record`: staff/day, check-in/out, computed hours, status and note.
- `leave_request`: requester, date range, reason, status and reviewer.
- `work_assignment`: order/task, quantity, due date, status and creator, with a
  many-to-many `work_assignment_assignee` join.
- `payroll_record`: staff/month, salary, days worked, advance, deductions,
  computed net and status; unique by staff/month.
- `payroll_payment`: payment history linked to a payroll record.
- `performance_feedback`: monthly quantity, on-time rate, feedback and author.
- `app_setting`: operational values such as shift start time.
- `audit_event`: actor, action, affected record, timestamp and summary.
- `password_reset_request`: staff recovery request, owner decision and review time.

The data models are implemented in the `staff` app and applied through Django
migrations.

## Install and run

Requires Python 3.10+ and MySQL 8. Create a database and least-privilege MySQL
user, then:

1. `python -m venv .venv`
2. PowerShell: `.venv\\Scripts\\Activate.ps1`
3. `python -m pip install -r requirements.txt`
4. Copy `.env.example` to `.env`; set a private random `DJANGO_SECRET_KEY` and
   your database values. Never commit `.env`.
5. In MySQL Workbench as an administrator, run `database_setup.sql` to create
   the database and grant the app account access.
6. `python manage.py makemigrations staff`
7. `python manage.py migrate`
8. `python manage.py createsuperuser` (the first owner account)
9. `python manage.py runserver`, then open <http://127.0.0.1:8000/login/>.

## Deploy to Vercel

Vercel detects this project from `manage.py` and collects static assets because
`STATIC_ROOT` is configured. Add these environment variables in the Vercel
Project Settings for Production:

- `DJANGO_SECRET_KEY`: use the private key generated for this project.
- `DJANGO_DEBUG`: `false`.
- `DJANGO_ALLOWED_HOSTS`: optional comma-separated custom hostnames. Vercel's
  `VERCEL_URL` and `VERCEL_PROJECT_PRODUCTION_URL` are allowed automatically.
- `DJANGO_CSRF_TRUSTED_ORIGINS`: optional comma-separated HTTPS origins for any
  custom domains. Vercel deployment domains are trusted automatically.
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`: Aiven connection
  values from the service's Connection information panel.
- `DB_SSL_CA_BASE64`: base64-encoded contents of the Aiven CA certificate;
  keep the local CA file out of source control.

The Aiven database migrations have already been applied. Do not run migrations
as part of every deployment. Create the first owner with
`python manage.py createsuperuser` after Vercel is linked to the project and
the same environment values are available locally. Vercel's function filesystem
is not durable storage, so staff profile photo uploads need an external object
storage backend before using uploads in production.

Staff can change passwords while signed in from the sidebar's **Change
password** option. The sign-in page's **Forgot password?** link creates a
request in **Access & Roles** and emails active owners when email is configured.
The owner can deny the request or set a temporary password; the staff member
must replace it at next sign-in. Temporary passwords are never emailed or
stored in plain text. Access requests create inactive accounts; owners approve
them and set an initial temporary password. Public password-based self-signup
is not available.

## Role access

- **Owner:** full access, including payroll, access control, and settings.
- **Manager:** staff directory, attendance and leave review, assignments, and
  performance. Managers cannot edit payroll, access roles, or settings.
- **Staff:** own profile, attendance/check-in/out, leave requests, assigned
  work progress, and their own pay slips. Cross-staff records are blocked.

Shift start defaults to 09:00 and can be changed in Settings. Work assignment
overdue status is computed from the due date. Attendance, leave decisions,
assignment changes, payroll, performance, staff, and setting actions are
recorded in the activity log.

Only the owner can create or edit attendance records, and the attendance form
accepts today's date only. Staff can check in and out for themselves once per
day; managers have read-only attendance access. The owner can download an
application data and staff-photo backup as a ZIP file from Settings. Its
`data.json` file is a Django fixture; restore it with `manage.py loaddata` and
place the included `media` files under the configured media root.
