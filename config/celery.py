"""Celery 앱 설정"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("config")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(["tasks"])

import tasks.calculate_risk  # noqa: F401,E402
import tasks.check_alerts  # noqa: F401,E402
import tasks.cleanup  # noqa: F401,E402
# autodiscover_tasks는 Django 앱의 tasks.py를 찾는 방식이므로
# 별도 tasks/ 패키지의 서브모듈은 명시적으로 import
import tasks.fetch_weather  # noqa: F401,E402
