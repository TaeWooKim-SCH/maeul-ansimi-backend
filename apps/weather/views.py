from datetime import timedelta

from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers as s
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WeatherAlert, WeatherForecast, WeatherObservation
from .serializers import (AirQualitySerializer, WeatherAlertSerializer,
                          WeatherForecastSerializer,
                          WeatherObservationSerializer)

# ---------- 대기질 등급 판정 ----------

PM25_GRADES = [(15, "좋음"), (35, "보통"), (75, "나쁨"), (float("inf"), "매우나쁨")]
OZONE_GRADES = [
    (0.03, "좋음"),
    (0.09, "보통"),
    (0.15, "나쁨"),
    (float("inf"), "매우나쁨"),
]


def _get_grade(value: float | None, thresholds: list[tuple[float, str]]) -> str:
    if value is None:
        return ""
    for limit, label in thresholds:
        if value <= limit:
            return label
    return ""


class CurrentWeatherView(APIView):
    """GET /api/weather/current/ — 최신 관측 + 활성 특보"""

    @extend_schema(
        tags=["기상"],
        responses=inline_serializer(
            name="CurrentWeather",
            fields={
                "observation": WeatherObservationSerializer(),
                "active_alerts": WeatherAlertSerializer(many=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        observation = WeatherObservation.objects.order_by("-observed_at").first()
        if observation is None:
            return Response({"detail": "기상 관측 데이터가 없습니다."}, status=404)

        now = timezone.now()
        active_alerts = WeatherAlert.objects.filter(
            issued_at__lte=now,
        ).exclude(effective_until__lt=now)

        return Response(
            {
                "observation": WeatherObservationSerializer(observation).data,
                "active_alerts": WeatherAlertSerializer(active_alerts, many=True).data,
            }
        )


class ForecastView(APIView):
    """GET /api/weather/forecast/ — 72시간 + 주간 예보"""

    @extend_schema(
        tags=["기상"],
        responses=inline_serializer(
            name="WeatherForecastResponse",
            fields={
                "hourly": WeatherForecastSerializer(many=True),
                "weekly": WeatherForecastSerializer(many=True),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        now = timezone.now()

        # 72시간 (3시간 간격)
        hourly = WeatherForecast.objects.filter(
            forecast_at__gte=now,
            forecast_at__lte=now + timedelta(hours=72),
        ).order_by("forecast_at")

        # 주간 (7일)
        weekly = WeatherForecast.objects.filter(
            forecast_at__gte=now,
            forecast_at__lte=now + timedelta(days=7),
        ).order_by("forecast_at")

        return Response(
            {
                "hourly": WeatherForecastSerializer(hourly, many=True).data,
                "weekly": WeatherForecastSerializer(weekly, many=True).data,
            }
        )


class WeatherAlertListView(APIView):
    """GET /api/weather/alerts/ — 발효중 기상특보 목록"""

    @extend_schema(
        tags=["기상"],
        responses=inline_serializer(
            name="WeatherAlertList",
            fields={
                "alerts": WeatherAlertSerializer(many=True),
                "has_active_alert": s.BooleanField(),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        now = timezone.now()
        alerts = WeatherAlert.objects.filter(
            issued_at__lte=now,
        ).exclude(effective_until__lt=now)

        return Response(
            {
                "alerts": WeatherAlertSerializer(alerts, many=True).data,
                "has_active_alert": alerts.exists(),
            }
        )


class AirQualityView(APIView):
    """GET /api/weather/air-quality/ — 최신 대기질"""

    @extend_schema(
        tags=["기상"],
        responses=inline_serializer(
            name="AirQuality",
            fields={
                "pm25": s.FloatField(allow_null=True),
                "pm25_grade": s.CharField(),
                "pm10": s.FloatField(allow_null=True),
                "ozone": s.FloatField(allow_null=True),
                "ozone_grade": s.CharField(),
                "observed_at": s.DateTimeField(),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        obs = WeatherObservation.objects.order_by("-observed_at").first()
        if obs is None:
            return Response({"detail": "대기질 데이터가 없습니다."}, status=404)

        pm25_val = float(obs.pm25) if obs.pm25 is not None else None
        ozone_val = float(obs.ozone) if obs.ozone is not None else None

        return Response(
            {
                "pm25": obs.pm25,
                "pm25_grade": _get_grade(pm25_val, PM25_GRADES),
                "pm10": obs.pm10,
                "ozone": obs.ozone,
                "ozone_grade": _get_grade(ozone_val, OZONE_GRADES),
                "observed_at": obs.observed_at,
            }
        )
