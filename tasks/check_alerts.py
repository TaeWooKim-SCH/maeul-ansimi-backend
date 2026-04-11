"""알림 자동 생성 Celery 태스크"""

import logging

from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# 등급 순서 (높을수록 위험)
LEVEL_ORDER: dict[str, int] = {
    "관심": 0,
    "주의": 1,
    "경계": 2,
    "심각": 3,
}

# 등급 상승 시 생성할 알림 유형
ALERT_TYPE_MAP: dict[str, str] = {
    "주의": "안부전화",
    "경계": "방문배정",
    "심각": "긴급출동",
}


def _is_level_escalated(prev_level: str | None, new_level: str) -> bool:
    """등급 상승 감지. prev가 None(첫 평가)이면 주의 이상만 트리거."""
    new_order = LEVEL_ORDER.get(new_level, 0)
    if prev_level is None:
        return new_order >= 1  # 주의 이상이면 알림
    prev_order = LEVEL_ORDER.get(prev_level, 0)
    return new_order > prev_order


def _send_guardian_notification(elder, alert) -> None:
    """보호자 알림 발송 (카카오 알림톡)."""
    if not elder.has_guardian or not elder.guardian_phone:
        return

    from common.notification import KakaoNotificationService

    svc = KakaoNotificationService()

    # 위험도 정보 조회
    top_factor = "위험등급 상승"
    score = 0
    if alert.risk_score:
        score = float(alert.risk_score.total_score)
        importance = alert.risk_score.feature_importance or {}
        if importance:
            top_key = max(importance, key=importance.get)
            top_factor = top_key

    result = svc.send(
        phone=elder.guardian_phone,
        template_key="보호자알림",
        variables={
            "elder_name": elder.name,
            "risk_level": alert.alert_level,
            "top_factor": top_factor,
        },
    )
    logger.info(
        "[보호자알림] %s님 → %s (%s)",
        elder.name,
        elder.guardian_phone,
        result.get("mode"),
    )


@shared_task(name="tasks.check_alerts.check_and_create_alerts")
def check_and_create_alerts() -> str:
    """위험도 계산 완료 후 등급 상승 감지 → 알림 자동 생성.

    각 대상자의 최신 2건 RiskScore를 비교하여 등급이 상승했으면 알림 생성.
    """
    from apps.alerts.models import Alert
    from apps.elders.models import Elder
    from apps.risk.models import RiskScore

    elders = Elder.objects.filter(is_deleted=False)
    created_count = 0

    for elder in elders.iterator(chunk_size=100):
        recent_scores = list(
            RiskScore.objects.filter(elder=elder)
            .order_by("-scored_at")
            .values_list("risk_level", "id")[:2]
        )

        if not recent_scores:
            continue

        new_level = recent_scores[0][0]
        new_score_id = recent_scores[0][1]
        prev_level = recent_scores[1][0] if len(recent_scores) > 1 else None

        if not _is_level_escalated(prev_level, new_level):
            continue

        # 알림 유형 결정
        alert_type = ALERT_TYPE_MAP.get(new_level)
        if alert_type is None:
            continue

        alert = Alert.objects.create(
            elder=elder,
            risk_score_id=new_score_id,
            alert_type=alert_type,
            alert_level=new_level,
            status="발송됨",
            note=f"위험 등급 상승: {prev_level or '없음'} → {new_level}",
        )
        created_count += 1

        # 경계/심각 시 보호자 알림 추가 생성
        if new_level in ("경계", "심각") and elder.has_guardian:
            guardian_alert = Alert.objects.create(
                elder=elder,
                risk_score_id=new_score_id,
                alert_type="보호자알림",
                alert_level=new_level,
                status="발송됨",
                note=f"보호자 알림: {new_level} 등급",
            )
            created_count += 1
            _send_guardian_notification(elder, guardian_alert)

    logger.info("알림 자동 생성 완료: %d건", created_count)
    return f"ok: {created_count} alerts created"
