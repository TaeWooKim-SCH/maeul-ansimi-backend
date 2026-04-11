"""위험도 계산 Celery 태스크"""

import logging

from celery import shared_task
from django.core.cache import cache

logger = logging.getLogger(__name__)


@shared_task(
    name="tasks.calculate_risk.calculate_all_risk",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def calculate_all_risk(self) -> str:
    """전체 대상자 위험도 일괄 계산.

    elders.iterator() 순회 → bulk_create → cache.delete('risk:heatmap')
    완료 후 check_and_create_alerts.delay() 체이닝
    """
    from apps.ai.engine import RiskScoringEngine
    from apps.elders.models import Elder
    from apps.risk.models import RiskScore
    from apps.weather.models import WeatherObservation
    from apps.weather.services import build_weather_condition

    try:
        # 최신 기상 데이터
        weather_obs = WeatherObservation.objects.order_by("-observed_at").first()
        weather_condition = build_weather_condition(weather_obs)

        engine = RiskScoringEngine()
        elders = Elder.objects.filter(is_deleted=False).iterator(chunk_size=100)
        risk_scores: list[RiskScore] = []

        for elder in elders:
            profile = elder.to_risk_profile()
            result = engine.calculate(profile, weather_condition)

            risk_scores.append(
                RiskScore(
                    elder=elder,
                    weather_risk=result["weather_risk"],
                    health_risk=result["health_risk"],
                    housing_risk=result["housing_risk"],
                    isolation_risk=result["isolation_risk"],
                    total_score=result["total_score"],
                    risk_level=result["risk_level"],
                    feature_importance=result.get("feature_importance", {}),
                    model_version=result["model_version"],
                )
            )

        if risk_scores:
            RiskScore.objects.bulk_create(risk_scores)

        # 캐시 무효화
        cache.delete("risk:heatmap")
        cache.delete("dashboard:overview")

        count = len(risk_scores)
        logger.info("전체 위험도 계산 완료: %d명", count)

        # 알림 체크 체이닝
        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts.delay()

        return f"ok: {count} elders"

    except Exception as exc:
        logger.exception("전체 위험도 계산 실패")
        raise self.retry(exc=exc)


@shared_task(name="tasks.calculate_risk.calculate_single_risk")
def calculate_single_risk(elder_id: int) -> str:
    """단건 위험도 계산 (등록/수정 시 호출)"""
    from apps.ai.engine import RiskScoringEngine
    from apps.elders.models import Elder
    from apps.risk.models import RiskScore
    from apps.weather.models import WeatherObservation
    from apps.weather.services import build_weather_condition

    try:
        elder = Elder.objects.get(pk=elder_id, is_deleted=False)
    except Elder.DoesNotExist:
        logger.warning("대상자 없음: %d", elder_id)
        return f"elder_not_found: {elder_id}"

    weather_obs = WeatherObservation.objects.order_by("-observed_at").first()
    weather_condition = build_weather_condition(weather_obs)

    engine = RiskScoringEngine()
    profile = elder.to_risk_profile()
    result = engine.calculate(profile, weather_condition)

    RiskScore.objects.create(
        elder=elder,
        weather_risk=result["weather_risk"],
        health_risk=result["health_risk"],
        housing_risk=result["housing_risk"],
        isolation_risk=result["isolation_risk"],
        total_score=result["total_score"],
        risk_level=result["risk_level"],
        feature_importance=result.get("feature_importance", {}),
        model_version=result["model_version"],
    )

    cache.delete("risk:heatmap")
    logger.info(
        "단건 위험도 계산 완료: elder=%d, level=%s", elder_id, result["risk_level"]
    )
    return f"ok: elder={elder_id}, level={result['risk_level']}"
