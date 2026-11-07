import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "")
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() in {"1", "true", "yes", "on"}
ALLOWED_HOSTS = [x.strip() for x in os.getenv("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if x.strip()]
CSRF_TRUSTED_ORIGINS = [x.strip() for x in os.getenv("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if x.strip()]
for vercel_domain in (os.getenv("VERCEL_URL", ""), os.getenv("VERCEL_PROJECT_PRODUCTION_URL", "")):
    vercel_domain = vercel_domain.strip().removeprefix("https://").removeprefix("http://").split("/", 1)[0]
    if vercel_domain:
        if vercel_domain not in ALLOWED_HOSTS:
            ALLOWED_HOSTS.append(vercel_domain)
        vercel_origin = f"https://{vercel_domain}"
        if vercel_origin not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(vercel_origin)
INSTALLED_APPS = ["django.contrib.admin", "django.contrib.auth", "django.contrib.contenttypes", "django.contrib.sessions", "django.contrib.messages", "django.contrib.staticfiles", "staff.apps.StaffConfig"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware", "django.contrib.sessions.middleware.SessionMiddleware", "django.middleware.common.CommonMiddleware", "django.middleware.csrf.CsrfViewMiddleware", "django.contrib.auth.middleware.AuthenticationMiddleware", "staff.middleware.MustChangePasswordMiddleware", "django.contrib.messages.middleware.MessageMiddleware", "django.middleware.clickjacking.XFrameOptionsMiddleware"]
ROOT_URLCONF = "ars_crm.urls"
TEMPLATES = [{"BACKEND": "django.template.backends.django.DjangoTemplates", "DIRS": [BASE_DIR / "templates"], "APP_DIRS": True, "OPTIONS": {"context_processors": ["django.template.context_processors.debug", "django.template.context_processors.request", "django.contrib.auth.context_processors.auth", "django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "ars_crm.wsgi.application"
ASGI_APPLICATION = "ars_crm.asgi.application"
db_options = {"charset": "utf8mb4"}
db_ssl_ca = os.getenv("DB_SSL_CA", "").strip()
db_ssl_ca_base64 = os.getenv("DB_SSL_CA_BASE64", "").strip()
if db_ssl_ca_base64:
    import base64
    import tempfile

    # Environment-variable input can preserve line breaks from PowerShell's
    # stdin pipe; remove whitespace while keeping strict character validation.
    ca_value = "".join(db_ssl_ca_base64.split())
    ca_contents = base64.b64decode(ca_value, validate=True).decode("utf-8")
    ca_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", prefix="ars-crm-db-ca-", delete=False)
    ca_file.write(ca_contents)
    ca_file.close()
    db_ssl_ca = ca_file.name
elif db_ssl_ca:
    # Deploy platforms can provide the CA as a PEM environment variable;
    # local development can point DB_SSL_CA at a downloaded .pem file.
    if "-----BEGIN CERTIFICATE-----" in db_ssl_ca:
        import tempfile

        ca_file = tempfile.NamedTemporaryFile(mode="w", suffix=".pem", prefix="ars-crm-db-ca-", delete=False)
        ca_file.write(db_ssl_ca)
        ca_file.close()
        db_ssl_ca = ca_file.name
    else:
        ca_path = Path(db_ssl_ca)
        if not ca_path.is_absolute():
            db_ssl_ca = str(BASE_DIR / ca_path)
if db_ssl_ca:
    db_options.update({"ssl_ca": db_ssl_ca, "ssl_verify_cert": True, "ssl_verify_identity": True})

DATABASES = {"default": {"ENGINE": "django.db.backends.mysql", "NAME": os.getenv("DB_NAME", "ars_garments_crm"), "USER": os.getenv("DB_USER", ""), "PASSWORD": os.getenv("DB_PASSWORD", ""), "HOST": os.getenv("DB_HOST", "127.0.0.1"), "PORT": os.getenv("DB_PORT", "3306"), "OPTIONS": db_options, "CONN_MAX_AGE": int(os.getenv("DB_CONN_MAX_AGE", "60"))}}
AUTH_USER_MODEL = "staff.StaffUser"
AUTH_PASSWORD_VALIDATORS = [{"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"}, {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"}, {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"}, {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"}]
LANGUAGE_CODE = "en-in"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = os.getenv("EMAIL_HOST", "")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "true").lower() in {"1", "true", "yes", "on"}
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "ARS Garments Staff CRM <no-reply@localhost>")

if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "3600"))
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
