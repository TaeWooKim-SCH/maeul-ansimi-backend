from decimal import Decimal
from typing import Any

from apps.risk.models import RiskScore
from apps.weather.models import WeatherObservation


def generate_recommendation(
    risk_score: RiskScore, weather: WeatherObservation | None = None
) -> dict[str, Any]:
    """등급 + 요인 + 기상 기반 조치 권고 생성"""
    level = risk_score.risk_level
    total = float(risk_score.total_score)
    factors = risk_score.feature_importance or {}

    # 상위 기여 요인 추출
    top_factors = sorted(factors.items(), key=lambda x: x[1], reverse=True)[:5]

    # 기상 컨텍스트
    weather_context: dict[str, Any] = {}
    if weather:
        weather_context = {
            "temperature": float(weather.temperature),
            "feels_like": float(weather.feels_like) if weather.feels_like else None,
            "humidity": float(weather.humidity) if weather.humidity else None,
            "pm25": float(weather.pm25) if weather.pm25 else None,
            "weather_alert": weather.weather_alert or None,
        }

    # 등급별 권고 조치
    recommendations: dict[str, dict[str, Any]] = {
        "심각": {
            "action": "긴급방문 및 보호자 긴급연락",
            "details": "119 출동 준비, 돌봄관리사 즉시 방문, 보호자 긴급 연락",
            "priority": "최우선",
        },
        "경계": {
            "action": "안부전화 및 보호자 알림",
            "details": "돌봄관리사 긴급 방문 배정, 보호자에게 상황 알림",
            "priority": "긴급",
        },
        "주의": {
            "action": "건강 가이드 제공",
            "details": "AI 안부 전화 확인, 건강 관리 안내 메시지 발송",
            "priority": "주의",
        },
        "관심": {
            "action": "정기 모니터링",
            "details": "정기 방문 일정에 따라 모니터링 유지",
            "priority": "일반",
        },
    }

    rec = recommendations.get(level, recommendations["관심"])

    # 기상 상황에 따른 추가 권고
    extra_advice: list[str] = []
    if weather:
        temp = float(weather.temperature)
        if temp >= 33:
            extra_advice.append("폭염 주의: 냉방장치 가동 확인, 수분 섭취 권고")
        elif temp <= -10:
            extra_advice.append("한파 주의: 난방장치 가동 확인, 동파 예방")
        if weather.pm25 and float(weather.pm25) > 75:
            extra_advice.append("미세먼지 나쁨: 외출 자제, 창문 닫기 권고")
        if weather.weather_alert:
            extra_advice.append(f"기상특보 발효중: {weather.weather_alert}")

    return {
        "risk_level": level,
        "total_score": total,
        "recommended_action": rec["action"],
        "action_details": rec["details"],
        "priority": rec["priority"],
        "top_factors": [{"factor": k, "contribution": v} for k, v in top_factors],
        "weather_context": weather_context,
        "extra_advice": extra_advice,
    }
