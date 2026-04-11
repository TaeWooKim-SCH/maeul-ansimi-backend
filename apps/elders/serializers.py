from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.risk.models import RiskScore

from .models import CareWorker, Elder

# ---------- 청양군 읍면 좌표 → region_code 매핑 ----------

CHEONGYANG_REGIONS: list[dict[str, Any]] = [
    {"code": "CY01", "name": "청양읍", "lat": 36.4592, "lng": 126.8022},
    {"code": "CY02", "name": "운곡면", "lat": 36.4939, "lng": 126.8435},
    {"code": "CY03", "name": "대치면", "lat": 36.5208, "lng": 126.7688},
    {"code": "CY04", "name": "정산면", "lat": 36.4172, "lng": 126.8658},
    {"code": "CY05", "name": "목면", "lat": 36.3892, "lng": 126.7939},
    {"code": "CY06", "name": "청남면", "lat": 36.3658, "lng": 126.8222},
    {"code": "CY07", "name": "장평면", "lat": 36.4439, "lng": 126.7353},
    {"code": "CY08", "name": "남양면", "lat": 36.3992, "lng": 126.7458},
]

VISIT_FREQ_SCORES: dict[str, Decimal] = {
    "매일": Decimal("10"),
    "주3회": Decimal("25"),
    "주2회": Decimal("35"),
    "주1회": Decimal("50"),
    "격주": Decimal("65"),
    "월1회": Decimal("80"),
    "없음": Decimal("95"),
}


def _map_region_code(lat: float | None, lng: float | None) -> str:
    """좌표 → 가장 가까운 청양군 읍면 코드 반환. 좌표 없으면 빈 문자열."""
    if lat is None or lng is None:
        return ""
    min_dist = float("inf")
    best_code = ""
    for region in CHEONGYANG_REGIONS:
        dist = (float(lat) - region["lat"]) ** 2 + (float(lng) - region["lng"]) ** 2
        if dist < min_dist:
            min_dist = dist
            best_code = region["code"]
    return best_code


def _calc_initial_isolation(
    lives_alone: bool, has_guardian: bool, care_visit_freq: str
) -> Decimal:
    """독거 + 보호자 + 방문주기 기반 초기 고립도 점수 계산"""
    score = Decimal("0")
    if lives_alone:
        score += Decimal("30")
    if not has_guardian:
        score += Decimal("20")
    score += VISIT_FREQ_SCORES.get(care_visit_freq, Decimal("50"))
    return min(score, Decimal("100"))


# ---------- 중첩 시리얼라이저 ----------


class CurrentRiskSerializer(serializers.ModelSerializer):
    class Meta:
        model = RiskScore
        fields = ("total_score", "risk_level", "scored_at")


class CareWorkerBriefSerializer(serializers.ModelSerializer):
    class Meta:
        model = CareWorker
        fields = ("id", "name", "phone", "region")


# ---------- Elder 시리얼라이저 ----------


class ElderListSerializer(serializers.ModelSerializer):
    current_risk = serializers.SerializerMethodField()

    class Meta:
        model = Elder
        fields = (
            "id",
            "name",
            "age",
            "gender",
            "address",
            "region_code",
            "diseases",
            "housing_type",
            "has_cooling",
            "lives_alone",
            "current_risk",
        )

    def get_current_risk(self, obj: Elder) -> dict | None:
        latest: RiskScore | None = obj.risk_scores.order_by("-scored_at").first()
        if latest is None:
            return None
        return CurrentRiskSerializer(latest).data


class ElderDetailSerializer(serializers.ModelSerializer):
    current_risk = serializers.SerializerMethodField()
    care_worker = CareWorkerBriefSerializer(read_only=True)

    class Meta:
        model = Elder
        exclude = ("is_deleted",)

    def get_current_risk(self, obj: Elder) -> dict | None:
        latest: RiskScore | None = obj.risk_scores.order_by("-scored_at").first()
        if latest is None:
            return None
        return {
            "total_score": latest.total_score,
            "risk_level": latest.risk_level,
            "weather_risk": latest.weather_risk,
            "health_risk": latest.health_risk,
            "housing_risk": latest.housing_risk,
            "isolation_risk": latest.isolation_risk,
            "scored_at": latest.scored_at,
            "feature_importance": latest.feature_importance,
        }


class ElderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Elder
        fields = (
            "name",
            "age",
            "gender",
            "address",
            "lat",
            "lng",
            "diseases",
            "bmi",
            "health_grade",
            "medications",
            "recent_hospital",
            "housing_type",
            "building_year",
            "has_cooling",
            "has_heating",
            "flood_risk",
            "lives_alone",
            "has_guardian",
            "guardian_phone",
            "care_visit_freq",
            "care_worker",
        )

    def validate_age(self, value: int) -> int:
        if value < 60:
            raise serializers.ValidationError("대상자 나이는 60세 이상이어야 합니다.")
        if value > 120:
            raise serializers.ValidationError("나이 값이 유효하지 않습니다.")
        return value

    def create(self, validated_data: dict) -> Elder:
        # disease_count 자동 계산
        diseases = validated_data.get("diseases", [])
        validated_data["disease_count"] = len(diseases) if diseases else 0

        # region_code 좌표 매핑
        validated_data["region_code"] = _map_region_code(
            validated_data.get("lat"), validated_data.get("lng")
        )

        # isolation_score 초기값
        validated_data["isolation_score"] = _calc_initial_isolation(
            validated_data.get("lives_alone", True),
            validated_data.get("has_guardian", False),
            validated_data.get("care_visit_freq", "주1회"),
        )

        elder = super().create(validated_data)

        # Celery 비동기 위험도 계산 트리거
        try:
            from tasks.calculate_risk import calculate_single_risk

            calculate_single_risk.delay(elder.pk)
        except Exception:
            pass  # 태스크 미구현 시 무시

        return elder
