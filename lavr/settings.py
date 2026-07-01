import os
from pathlib import Path

from django.contrib import messages

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = "django-insecure-#nbo&g5h6(nxz*r+07%-2l33=a^rlrnjhydt#n#birz=_!)3fz"

DEBUG = True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'apps',
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lavr.urls"
AUTH_USER_MODEL = "apps.User"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / 'templates']
        ,
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "lavr.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "static"
# STATICFILES_DIRS = [BASE_DIR / 'static']  # agar static papka bo'lsa

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

MESSAGE_TAGS = {messages.ERROR: 'error'}


# ─── 2. AUTH — login/logout yo'naltirish ──────────────────────
# Aynan shu narsa yo'qligi sababli /accounts/login/?next=/ ga
# tushib, 404 chiqargan edi. Django default holatda shu manzilni
# qidiradi, agar siz boshqacha belgilamagan bo'lsangiz.

LOGIN_URL = 'login'  # urls.py dagi name='login' bilan moslashadi
LOGIN_REDIRECT_URL = 'dashboard'  # kirgandan keyin qayerga yo'naltirilsin
LOGOUT_REDIRECT_URL = 'login'  # chiqgandan keyin qayerga yo'naltirilsin


# ─── 5. MESSAGES — Bootstrap/Tailwind class nomlariga moslash ──
from django.contrib.messages import constants as messages_constants
MESSAGE_TAGS = {
    messages_constants.DEBUG: 'info',
    messages_constants.INFO: 'info',
    messages_constants.SUCCESS: 'success',
    messages_constants.WARNING: 'warning',
    messages_constants.ERROR: 'error',
}

# TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
# TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# Development uchun vaqtincha to'g'ridan-to'g'ri yozish mumkin (ishonchli
# bo'lmagan joyda saqlamang, productionga chiqishdan oldin o'chiring):
TELEGRAM_BOT_TOKEN = '8656172686:AAHCC8alm0pX8u9h8JiUDx7tPPP6yueZe7A'
TELEGRAM_CHAT_ID = '6196411524'
