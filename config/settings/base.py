"""공통 설정 — 개발/운영 환경 공유"""

import os
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
)
environ.Env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY", default="django-insecure-change-me-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "django_filters",
    "corsheaders",
    "django_celery_beat",
    "drf_spectacular",
]

LOCAL_APPS = [
    "apps.elders",
    "apps.risk",
    "apps.weather",
    "apps.alerts",
    "apps.dashboard",
    "apps.ai",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",  # CORS — CommonMiddleware 앞에 위치
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3"),
}

# ---------------------------------------------------------------------------
# Password validation
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Internationalization
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "common.pagination.StandardPagination",
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "EXCEPTION_HANDLER": "common.exceptions.custom_exception_handler",
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

# ---------------------------------------------------------------------------
# drf-spectacular (API 문서)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "마을안심이 API",
    "DESCRIPTION": "충남 청양군 고령 독거노인 AI 안전관리 플랫폼 백엔드 API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "PREPROCESSING_HOOKS": ["config.spectacular.preprocess_tag_by_url"],
    "TAGS": [
        {"name": "대상자", "description": "고령 독거노인 CRUD"},
        {"name": "위험도", "description": "AI 위험도 평가 조회"},
        {"name": "기상", "description": "기상/대기질 데이터"},
        {"name": "알림", "description": "알림 이력 및 응답"},
        {"name": "대시보드", "description": "종합 현황판"},
        {"name": "AI", "description": "위험도 계산 트리거"},
    ],
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ORIGINS", default=["http://localhost:3000"])

# ---------------------------------------------------------------------------
# Redis / Cache
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": REDIS_URL,
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Seoul"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "fetch-weather-observation": {
        "task": "tasks.fetch_weather.fetch_weather_observation",
        "schedule": crontab(minute="*/30"),
    },
    "fetch-weather-forecast": {
        "task": "tasks.fetch_weather.fetch_weather_forecast",
        "schedule": crontab(minute=0, hour="*/3"),
    },
    "fetch-weather-alert": {
        "task": "tasks.fetch_weather.fetch_weather_alert",
        "schedule": crontab(minute="*/10"),
    },
    "fetch-air-quality": {
        "task": "tasks.fetch_weather.fetch_air_quality",
        "schedule": crontab(minute=0, hour="*/1"),
    },
    "calculate-all-risk": {
        "task": "tasks.calculate_risk.calculate_all_risk",
        "schedule": crontab(minute=0, hour="*/1"),
    },
    "cleanup-old-data": {
        "task": "tasks.cleanup.cleanup_old_data",
        "schedule": crontab(minute=0, hour=3),
    },
    "fetch-living-weather-index": {
        "task": "tasks.fetch_weather.fetch_living_weather_index",
        "schedule": crontab(minute=0, hour="*/3"),
    },
    "fetch-mid-forecast": {
        "task": "tasks.fetch_weather.fetch_mid_forecast",
        "schedule": crontab(minute=30, hour="*/6"),
    },
}

# ---------------------------------------------------------------------------
# 공공데이터 API
# ---------------------------------------------------------------------------
DATA_GO_KR_API_KEY = env("DATA_GO_KR_API_KEY", default="")
WEATHER_STATION_IDS = env("WEATHER_STATION_IDS", default="238")
WEATHER_NX = env.int("WEATHER_NX", default=65)
WEATHER_NY = env.int("WEATHER_NY", default=99)
AIR_QUALITY_STATION = env("AIR_QUALITY_STATION", default="청양")
RISK_CALC_INTERVAL_MINUTES = env.int("RISK_CALC_INTERVAL_MINUTES", default=60)
WEATHER_FETCH_INTERVAL_MINUTES = env.int("WEATHER_FETCH_INTERVAL_MINUTES", default=30)
