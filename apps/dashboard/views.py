from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.core.cache import cache
from django.db.models import Count, Max, OuterRef, Subquery
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.alerts.models import Alert
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import (WeatherAlert, WeatherForecast,
                                 WeatherObservation)

PERIOD_MAP: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class DashboardOverviewView(APIView):
    """GET /api/dashboard/overview/ — 종합 대시보드"""

    CACHE_KEY = "dashboard:overview"
    CACHE_TTL = 30

    @extend_schema(
        tags=["대시보드"],
        responses=inline_serializer(
            name="DashboardOverview",
            fields={
                "total_elders": s.IntegerField(),
                "risk_counts": s.DictField(child=s.IntegerField()),
                "today_alerts": s.IntegerField(),
                "unresponded_alerts": s.IntegerField(),
                "response_rate": s.FloatField(),
                "weather_summary": s.DictField(),
                "last_risk_calc": s.DateTimeField(allow_null=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        cached = cache.get(self.CACHE_KEY)
        if cached is not None:
            return Response(cached)

        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # 전체 대상자 수
        total_elders = Elder.objects.filter(is_deleted=False).count()

        # 등급별 수 (최신 RiskScore 기준)
        latest_level = Subquery(
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("risk_level")[:1]
        )
        elders_with_level = (
            Elder.objects.filter(is_deleted=False)
            .annotate(current_level=latest_level)
            .exclude(current_level__isnull=True)
        )

        risk_counts: dict[str, int] = {}
        for level_code, _ in RiskScore.RISK_LEVEL_CHOICES:
            risk_counts[level_code] = elders_with_level.filter(
                current_level=level_code
            ).count()

        # 오늘 알림
        today_alerts = Alert.objects.filter(created_at__gte=today_start)
        today_total = today_alerts.count()
        today_unresponded = today_alerts.filter(status__in=["발송됨", "미응답"]).count()
        today_responded = today_alerts.filter(status="응답완료").count()
        response_rate = (
            round(today_responded / today_total * 100, 1) if today_total > 0 else 0.0
        )

        # 기상 요약
        weather = WeatherObservation.objects.order_by("-observed_at").first()
        weather_summary: dict[str, Any] = {}
        if weather:
            weather_summary = {
                "temperature": float(weather.temperature),
                "feels_like": float(weather.feels_like) if weather.feels_like else None,
                "humidity": float(weather.humidity) if weather.humidity else None,
                "pm25": float(weather.pm25) if weather.pm25 else None,
                "observed_at": weather.observed_at,
            }

        # 활성 기상특보 (유무 + 특보명)
        active_alerts = (
            WeatherAlert.objects.filter(issued_at__lte=now)
            .exclude(effective_until__lt=now)
            .order_by("-issued_at")
        )
        weather_summary["has_active_alert"] = active_alerts.exists()
        first_alert = active_alerts.first()
        weather_summary["active_alert_type"] = (
            first_alert.alert_type if first_alert else None
        )

        # 내일 예보
        tomorrow_start = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        tomorrow_end = tomorrow_start + timedelta(days=1)
        tomorrow_fcst = (
            WeatherForecast.objects.filter(
                forecast_at__gte=tomorrow_start,
                forecast_at__lt=tomorrow_end,
            )
            .order_by("forecast_at")
            .first()
        )
        weather_summary["tomorrow_forecast"] = None
        if tomorrow_fcst:
            weather_summary["tomorrow_forecast"] = {
                "temperature": float(tomorrow_fcst.temperature),
                "sky_condition": tomorrow_fcst.sky_condition,
            }

        # 최근 위험도 계산 시각
        last_risk_calc = RiskScore.objects.aggregate(last=Max("scored_at"))["last"]

        data = {
            "total_elders": total_elders,
            "risk_counts": risk_counts,
            "today_alerts": today_total,
            "unresponded_alerts": today_unresponded,
            "response_rate": response_rate,
            "weather_summary": weather_summary,
            "last_risk_calc": last_risk_calc,
        }

        cache.set(self.CACHE_KEY, data, self.CACHE_TTL)
        return Response(data)


class DashboardChartsView(APIView):
    """GET /api/dashboard/charts/?period=24h — 시간별 등급 변화 + 기온"""

    @extend_schema(
        tags=["대시보드"],
        responses=inline_serializer(
            name="DashboardCharts",
            fields={
                "period": s.CharField(),
                "data": s.ListField(child=s.DictField()),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        period_key = request.query_params.get("period", "24h")
        delta = PERIOD_MAP.get(period_key, PERIOD_MAP["24h"])
        since = timezone.now() - delta

        # 위험도 시계열 — scored_at 기준으로 시간 그룹핑
        scores = RiskScore.objects.filter(scored_at__gte=since).order_by("scored_at")

        time_buckets: dict[str, dict[str, int]] = defaultdict(
            lambda: {"심각": 0, "경계": 0, "주의": 0, "관심": 0}
        )
        for score in scores.values("scored_at", "risk_level"):
            hour_key = score["scored_at"].strftime("%Y-%m-%d %H:00")
            time_buckets[hour_key][score["risk_level"]] += 1

        # 기온 시계열
        observations = WeatherObservation.objects.filter(
            observed_at__gte=since
        ).order_by("observed_at")
        temp_map: dict[str, float] = {}
        for obs in observations.values("observed_at", "temperature"):
            hour_key = obs["observed_at"].strftime("%Y-%m-%d %H:00")
            temp_map[hour_key] = float(obs["temperature"])

        # 합성
        all_times = sorted(set(list(time_buckets.keys()) + list(temp_map.keys())))
        data_points: list[dict[str, Any]] = []
        for t in all_times:
            entry: dict[str, Any] = {"time": t}
            if t in time_buckets:
                entry.update(time_buckets[t])
            if t in temp_map:
                entry["temperature"] = temp_map[t]
            data_points.append(entry)

        return Response({"period": period_key, "data": data_points})


class RecentAlertsView(APIView):
    """GET /api/dashboard/recent-alerts/ — 실시간 알림 패널용"""

    @extend_schema(
        tags=["대시보드"],
        responses=inline_serializer(
            name="RecentAlerts",
            fields={
                "results": s.ListField(child=s.DictField()),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        alerts = Alert.objects.select_related("elder", "risk_score").order_by(
            "-created_at"
        )[:10]

        results: list[dict[str, Any]] = []
        for alert in alerts:
            elder = alert.elder
            risk = alert.risk_score

            top_factors: list[str] = []
            if risk and risk.feature_importance:
                sorted_factors = sorted(
                    risk.feature_importance.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )
                top_factors = [f"{k}:{v}" for k, v in sorted_factors[:2]]

            results.append(
                {
                    "id": alert.pk,
                    "elder": {
                        "id": elder.pk,
                        "name": elder.name,
                        "age": elder.age,
                        "region_code": elder.region_code,
                    },
                    "risk_score": {
                        "total_score": float(risk.total_score) if risk else None,
                        "risk_level": risk.risk_level if risk else None,
                        "top_factors": top_factors,
                    },
                    "alert_type": alert.alert_type,
                    "alert_level": alert.alert_level,
                    "status": alert.status,
                    "sent_at": alert.sent_at,
                    "note": alert.note,
                }
            )

        return Response({"results": results})
