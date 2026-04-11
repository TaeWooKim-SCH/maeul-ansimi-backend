from django.db import models
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.elders.models import Elder
from apps.risk.models import RiskScore


class CalculateRiskView(APIView):
    """POST /api/ai/calculate-risk/ — 수동 위험도 재계산 트리거"""

    @extend_schema(
        tags=["AI"],
        request=inline_serializer(
            name="CalculateRiskRequest",
            fields={"elder_id": s.IntegerField(required=False, allow_null=True)},
        ),
        responses={
            202: inline_serializer(
                name="CalculateRiskResponse",
                fields={
                    "message": s.CharField(),
                    "task_id": s.CharField(),
                    "elder_id": s.IntegerField(required=False),
                },
            ),
        },
    )
    def post(self, request: Request) -> Response:
        elder_id = request.data.get("elder_id")

        try:
            if elder_id:
                # 단건 계산
                elder = get_object_or_404(Elder, pk=elder_id, is_deleted=False)
                from tasks.calculate_risk import calculate_single_risk

                result = calculate_single_risk.delay(elder.pk)
                return Response(
                    {
                        "message": f"대상자 {elder.name}의 위험도 재계산이 시작되었습니다.",
                        "task_id": result.id,
                        "elder_id": elder.pk,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            else:
                # 전체 계산
                from tasks.calculate_risk import calculate_all_risk

                result = calculate_all_risk.delay()
                return Response(
                    {
                        "message": "전체 대상자 위험도 재계산이 시작되었습니다.",
                        "task_id": result.id,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
        except ImportError:
            return Response(
                {"detail": "Celery 태스크가 아직 구현되지 않았습니다."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )


class FeatureImportanceView(APIView):
    """GET /api/ai/feature-importance/{elder_id}/ — 요인별 기여도"""

    @extend_schema(
        tags=["AI"],
        responses=inline_serializer(
            name="FeatureImportance",
            fields={
                "elder_id": s.IntegerField(),
                "elder_name": s.CharField(),
                "total_score": s.FloatField(),
                "risk_level": s.CharField(),
                "scored_at": s.DateTimeField(),
                "contributions": s.ListField(child=s.DictField()),
            },
        ),
    )
    def get(self, request: Request, elder_id: int) -> Response:
        elder = get_object_or_404(Elder, pk=elder_id, is_deleted=False)
        latest: RiskScore | None = elder.risk_scores.order_by("-scored_at").first()

        if latest is None:
            return Response({"detail": "위험도 평가 내역이 없습니다."}, status=404)

        importance = latest.feature_importance or {}
        contributions = sorted(
            [
                {"factor": k, "category": _categorize_factor(k), "contribution": v}
                for k, v in importance.items()
            ],
            key=lambda x: x["contribution"],
            reverse=True,
        )

        return Response(
            {
                "elder_id": elder.pk,
                "elder_name": elder.name,
                "total_score": float(latest.total_score),
                "risk_level": latest.risk_level,
                "scored_at": latest.scored_at,
                "contributions": contributions,
            }
        )


# 요인 → 카테고리 매핑
_FACTOR_CATEGORIES: dict[str, str] = {
    "temperature": "기상",
    "feels_like": "기상",
    "humidity": "기상",
    "pm25": "기상",
    "weather_alert": "기상",
    "wind_speed": "기상",
    "precipitation": "기상",
    "diseases": "건강",
    "disease_count": "건강",
    "bmi": "건강",
    "health_grade": "건강",
    "recent_hospital": "건강",
    "medications": "건강",
    "housing_type": "주거",
    "building_year": "주거",
    "has_cooling": "주거",
    "has_heating": "주거",
    "flood_risk": "주거",
    "lives_alone": "고립",
    "has_guardian": "고립",
    "care_visit_freq": "고립",
    "isolation_score": "고립",
    "last_contact": "고립",
}


def _categorize_factor(factor: str) -> str:
    return _FACTOR_CATEGORIES.get(factor, "기타")


class ModelInfoView(APIView):
    """GET /api/ai/model-info/ — AI 모델 정보/버전"""

    @extend_schema(
        tags=["AI"],
        responses=inline_serializer(
            name="ModelInfo",
            fields={
                "model_version": s.CharField(),
                "algorithm": s.CharField(),
                "weights": s.DictField(child=s.FloatField()),
                "level_thresholds": s.DictField(child=s.IntegerField()),
                "features_count": s.IntegerField(),
                "cross_risk_pairs": s.IntegerField(),
                "last_updated": s.DateTimeField(allow_null=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        from apps.ai.engine import (CROSS_RISK_TABLE, LEVEL_THRESHOLDS,
                                    MODEL_VERSION, WEIGHTS)

        last_calc = RiskScore.objects.aggregate(
            last=models.Max("scored_at"),
        )["last"]

        return Response(
            {
                "model_version": MODEL_VERSION,
                "algorithm": "규칙 기반 가중합산 + 교차위험 보정",
                "weights": WEIGHTS,
                "level_thresholds": {
                    level: int(threshold) for threshold, level in LEVEL_THRESHOLDS
                },
                "features_count": len(_FACTOR_CATEGORIES),
                "cross_risk_pairs": len(CROSS_RISK_TABLE),
                "last_updated": last_calc,
            }
        )
