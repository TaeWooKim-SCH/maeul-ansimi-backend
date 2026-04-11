from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Avg, Count, Max, OuterRef, Subquery
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.elders.models import Elder
from apps.weather.models import WeatherObservation

from .models import RiskScore
from .serializers import (CurrentRiskListSerializer, HeatmapSerializer,
                          RiskScoreSerializer)
from .services import generate_recommendation

# ---------- 기간 파라미터 → timedelta 변환 ----------

PERIOD_MAP: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class CurrentRiskListView(APIView):
    """GET /api/risk/current/ — 전체 대상자 최신 위험도"""

    @extend_schema(tags=["위험도"], responses=CurrentRiskListSerializer(many=True))
    def get(self, request: Request) -> Response:
        latest_score = (
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("total_score")[:1]
        )
        latest_level = (
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("risk_level")[:1]
        )
        latest_scored_at = (
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("scored_at")[:1]
        )

        qs = (
            Elder.objects.filter(is_deleted=False)
            .annotate(
                latest_total_score=Subquery(latest_score),
                latest_risk_level=Subquery(latest_level),
                latest_scored_at=Subquery(latest_scored_at),
            )
            .exclude(latest_total_score__isnull=True)
        )

        # level 필터
        level = request.query_params.get("level")
        if level:
            levels = [v.strip() for v in level.split(",") if v.strip()]
            qs = qs.filter(latest_risk_level__in=levels)

        qs = qs.order_by("-latest_total_score")
        serializer = CurrentRiskListSerializer(qs, many=True)
        return Response(serializer.data)


class ElderRiskDetailView(APIView):
    """GET /api/risk/elder/{id}/ — 개별 상세 위험도"""

    @extend_schema(
        tags=["위험도"],
        responses=inline_serializer(
            name="ElderRiskDetail",
            fields={
                "elder_id": s.IntegerField(),
                "elder_name": s.CharField(),
                "total_score": s.FloatField(),
                "risk_level": s.CharField(),
                "weather_risk": s.FloatField(),
                "health_risk": s.FloatField(),
                "housing_risk": s.FloatField(),
                "isolation_risk": s.FloatField(),
                "top_factors": s.ListField(child=s.CharField()),
                "recommended_action": s.CharField(),
                "weather_context": s.DictField(allow_null=True),
                "scored_at": s.DateTimeField(),
            },
        ),
    )
    def get(self, request: Request, elder_id: int) -> Response:
        elder = get_object_or_404(Elder, pk=elder_id, is_deleted=False)
        latest: RiskScore | None = elder.risk_scores.order_by("-scored_at").first()

        if latest is None:
            return Response({"detail": "위험도 평가 내역이 없습니다."}, status=404)

        # 최신 기상 데이터
        weather: WeatherObservation | None = WeatherObservation.objects.order_by(
            "-observed_at"
        ).first()

        result = generate_recommendation(latest, weather)
        result["elder_id"] = elder.pk
        result["elder_name"] = elder.name
        result["weather_risk"] = float(latest.weather_risk)
        result["health_risk"] = float(latest.health_risk)
        result["housing_risk"] = float(latest.housing_risk)
        result["isolation_risk"] = float(latest.isolation_risk)
        result["scored_at"] = latest.scored_at

        return Response(result)


class ElderRiskHistoryView(APIView):
    """GET /api/risk/elder/{id}/history/?period=24h — 위험도 이력"""

    @extend_schema(tags=["위험도"], responses=RiskScoreSerializer(many=True))
    def get(self, request: Request, elder_id: int) -> Response:
        elder = get_object_or_404(Elder, pk=elder_id, is_deleted=False)
        period_key = request.query_params.get("period", "24h")
        delta = PERIOD_MAP.get(period_key, PERIOD_MAP["24h"])
        since = timezone.now() - delta

        scores = elder.risk_scores.filter(scored_at__gte=since).order_by("scored_at")
        serializer = RiskScoreSerializer(scores, many=True)
        return Response(
            {"elder_id": elder.pk, "period": period_key, "history": serializer.data}
        )


class RiskSummaryView(APIView):
    """GET /api/risk/summary/ — 등급별 통계"""

    @extend_schema(
        tags=["위험도"],
        responses=inline_serializer(
            name="RiskSummary",
            fields={
                "total": s.IntegerField(),
                "by_level": s.DictField(child=s.IntegerField()),
                "avg_score": s.FloatField(allow_null=True),
                "max_score": s.FloatField(allow_null=True),
                "calculated_at": s.DateTimeField(allow_null=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        # Elder별 최신 RiskScore id — Subquery 방식
        latest_id_subquery = Subquery(
            RiskScore.objects.filter(elder_id=OuterRef("pk"))
            .order_by("-scored_at")
            .values("id")[:1]
        )
        latest_score_ids = (
            Elder.objects.filter(is_deleted=False)
            .annotate(latest_risk_id=latest_id_subquery)
            .exclude(latest_risk_id__isnull=True)
            .values_list("latest_risk_id", flat=True)
        )
        latest_scores = RiskScore.objects.filter(id__in=latest_score_ids)

        by_level: dict[str, int] = {}
        for level_code, _level_name in RiskScore.RISK_LEVEL_CHOICES:
            by_level[level_code] = latest_scores.filter(risk_level=level_code).count()

        agg = latest_scores.aggregate(
            avg_score=Avg("total_score"),
            max_score=Max("total_score"),
            latest_calc=Max("scored_at"),
        )

        return Response(
            {
                "total": latest_scores.count(),
                "by_level": by_level,
                "avg_score": agg["avg_score"],
                "max_score": agg["max_score"],
                "calculated_at": agg["latest_calc"],
            }
        )


class HeatmapView(APIView):
    """GET /api/risk/heatmap/ — 지도용 히트맵 (Redis 캐시 60초)"""

    CACHE_KEY = "risk:heatmap"
    CACHE_TTL = 60

    @extend_schema(tags=["위험도"], responses=HeatmapSerializer(many=True))
    def get(self, request: Request) -> Response:
        cached = cache.get(self.CACHE_KEY)
        if cached is not None:
            return Response(cached)

        latest_score = (
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("total_score")[:1]
        )
        latest_level = (
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("risk_level")[:1]
        )

        qs = (
            Elder.objects.filter(is_deleted=False, lat__isnull=False, lng__isnull=False)
            .annotate(
                latest_total_score=Subquery(latest_score),
                latest_risk_level=Subquery(latest_level),
            )
            .exclude(latest_total_score__isnull=True)
        )

        serializer = HeatmapSerializer(qs, many=True)
        cache.set(self.CACHE_KEY, serializer.data, self.CACHE_TTL)
        return Response(serializer.data)
