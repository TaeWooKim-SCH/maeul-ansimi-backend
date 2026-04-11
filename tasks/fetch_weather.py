"""기상/대기질 데이터 수집 Celery 태스크"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(name="tasks.fetch_weather.fetch_weather_observation")
def fetch_weather_observation() -> str:
    """초단기실황 관측 데이터 수집 (30분 주기)"""
    from apps.weather.models import WeatherObservation
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    data = svc.get_weather_observation()

    if not data or "temperature" not in data:
        logger.warning("기상 관측 데이터 파싱 실패: %s", data)
        return "no_data"

    observed_at = data.get("observed_at", timezone.now())
    if timezone.is_naive(observed_at):
        from django.utils.timezone import make_aware

        observed_at = make_aware(observed_at)

    WeatherObservation.objects.create(
        observed_at=observed_at,
        temperature=data.get("temperature", 0),
        feels_like=data.get("feels_like"),
        humidity=data.get("humidity"),
        wind_speed=data.get("wind_speed"),
        precipitation=data.get("precipitation", 0),
    )

    logger.info("기상 관측 저장 완료: %s℃", data.get("temperature"))
    return f"ok: {data.get('temperature')}℃"


@shared_task(name="tasks.fetch_weather.fetch_weather_forecast")
def fetch_weather_forecast() -> str:
    """단기예보 수집 (3시간 주기)"""
    from apps.weather.models import WeatherForecast
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    forecasts = svc.get_weather_forecast()

    if not forecasts:
        logger.warning("예보 데이터 없음")
        return "no_data"

    objs = []
    for fc in forecasts:
        forecast_at = fc.get("forecast_at")
        if forecast_at is None:
            continue
        if timezone.is_naive(forecast_at):
            from django.utils.timezone import make_aware

            forecast_at = make_aware(forecast_at)

        objs.append(
            WeatherForecast(
                forecast_at=forecast_at,
                temperature=fc.get("temperature", 0),
                humidity=fc.get("humidity"),
                precipitation_prob=fc.get("precipitation_prob", 0),
                sky_condition=fc.get("sky_condition", ""),
            )
        )

    if objs:
        # 기존 미래 예보 삭제 후 새로 삽입
        WeatherForecast.objects.filter(forecast_at__gte=timezone.now()).delete()
        WeatherForecast.objects.bulk_create(objs)

    logger.info("예보 %d건 저장 완료", len(objs))
    return f"ok: {len(objs)} forecasts"


@shared_task(name="tasks.fetch_weather.fetch_weather_alert")
def fetch_weather_alert() -> str:
    """기상특보 수집 (10분 주기) — 특보 변경 시 위험도 재계산 트리거"""
    from apps.weather.models import WeatherAlert
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    alerts = svc.get_weather_alerts()

    # 현재 활성 특보 수
    now = timezone.now()
    prev_count = (
        WeatherAlert.objects.filter(
            issued_at__lte=now,
        )
        .exclude(effective_until__lt=now)
        .count()
    )

    new_count = 0
    for alert_data in alerts:
        issued_at = alert_data.get("issued_at")
        if issued_at is None:
            continue
        if timezone.is_naive(issued_at):
            from django.utils.timezone import make_aware

            issued_at = make_aware(issued_at)

        _, created = WeatherAlert.objects.get_or_create(
            alert_type=alert_data["alert_type"],
            issued_at=issued_at,
            defaults={
                "region": alert_data.get("region", "충남 청양군"),
            },
        )
        if created:
            new_count += 1

    # 특보 변경 감지 → 전체 위험도 재계산 즉시 트리거
    if new_count > 0:
        logger.info("새 기상특보 %d건 → 전체 위험도 재계산 트리거", new_count)
        from tasks.calculate_risk import calculate_all_risk

        calculate_all_risk.delay()

    logger.info("기상특보 처리 완료: 신규 %d건", new_count)
    return f"ok: {new_count} new alerts"


@shared_task(name="tasks.fetch_weather.fetch_air_quality")
def fetch_air_quality() -> str:
    """대기질 데이터 수집 (1시간 주기)"""
    from apps.weather.models import WeatherObservation
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    data = svc.get_air_quality()

    if not data:
        logger.warning("대기질 데이터 없음")
        return "no_data"

    # 최신 관측에 대기질 정보 업데이트
    latest = WeatherObservation.objects.order_by("-observed_at").first()
    if latest:
        if data.get("pm25") is not None:
            latest.pm25 = data["pm25"]
            latest.pm25_grade = data.get("pm25_grade", "")
        if data.get("pm10") is not None:
            latest.pm10 = data["pm10"]
        if data.get("ozone") is not None:
            latest.ozone = data["ozone"]
        latest.save(update_fields=["pm25", "pm25_grade", "pm10", "ozone"])
        logger.info(
            "대기질 업데이트: PM2.5=%s, PM10=%s", data.get("pm25"), data.get("pm10")
        )
    else:
        logger.warning("대기질 업데이트할 관측 데이터 없음")

    return f"ok: pm25={data.get('pm25')}"


@shared_task(name="tasks.fetch_weather.fetch_living_weather_index")
def fetch_living_weather_index() -> str:
    """생활기상지수 수집 (3시간 주기) — 더위체감지수 + 체감온도지수"""
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    data = svc.get_living_weather_index()

    if not data:
        logger.warning("생활기상지수 데이터 없음")
        return "no_data"

    logger.info("생활기상지수 수집 완료: %s", data)
    return f"ok: heat={data.get('heat_index', {}).get('today')}"


@shared_task(name="tasks.fetch_weather.fetch_mid_forecast")
def fetch_mid_forecast() -> str:
    """중기예보 수집 (6시간 주기) — 중기기온 + 중기육상예보"""
    from apps.weather.services import WeatherServiceWithFallback

    svc = WeatherServiceWithFallback()
    data = svc.get_mid_forecast()

    if not data:
        logger.warning("중기예보 데이터 없음")
        return "no_data"

    logger.info("중기예보 수집 완료")
    return "ok: mid_forecast fetched"
