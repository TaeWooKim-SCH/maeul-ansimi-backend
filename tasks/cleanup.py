"""데이터 정리 Celery 태스크"""

import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="tasks.cleanup.cleanup_old_data")
def cleanup_old_data() -> str:
    """30일 초과 WeatherObservation 삭제 (매일 03:00)"""
    from apps.weather.models import WeatherObservation

    cutoff = timezone.now() - timedelta(days=30)
    deleted_count, _ = WeatherObservation.objects.filter(
        observed_at__lt=cutoff
    ).delete()

    logger.info("오래된 기상 관측 데이터 삭제: %d건", deleted_count)
    return f"ok: deleted {deleted_count}"
