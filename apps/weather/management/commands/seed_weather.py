"""5개 기상 시나리오 시드 데이터 생성"""

from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.weather.models import (WeatherAlert, WeatherForecast,
                                 WeatherObservation)

# 시나리오 정의
SCENARIOS: dict[str, dict] = {
    "폭염": {
        "temperature": Decimal("36.5"),
        "feels_like": Decimal("40.2"),
        "humidity": Decimal("72.0"),
        "wind_speed": Decimal("1.2"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("28.0"),
        "pm25_grade": "보통",
        "pm10": Decimal("45.0"),
        "ozone": Decimal("0.06"),
        "weather_alert": "폭염경보: 충남 청양군",
        "alert_type": "폭염",
    },
    "한파": {
        "temperature": Decimal("-15.3"),
        "feels_like": Decimal("-23.1"),
        "humidity": Decimal("35.0"),
        "wind_speed": Decimal("8.5"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("22.0"),
        "pm25_grade": "보통",
        "pm10": Decimal("38.0"),
        "ozone": Decimal("0.02"),
        "weather_alert": "한파경보: 충남 청양군",
        "alert_type": "한파",
    },
    "호우": {
        "temperature": Decimal("24.0"),
        "feels_like": Decimal("26.5"),
        "humidity": Decimal("95.0"),
        "wind_speed": Decimal("12.0"),
        "precipitation": Decimal("85.0"),
        "pm25": Decimal("12.0"),
        "pm25_grade": "좋음",
        "pm10": Decimal("20.0"),
        "ozone": Decimal("0.02"),
        "weather_alert": "호우경보: 충남 청양군",
        "alert_type": "호우",
    },
    "미세먼지": {
        "temperature": Decimal("18.0"),
        "feels_like": Decimal("18.0"),
        "humidity": Decimal("55.0"),
        "wind_speed": Decimal("2.0"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("120.0"),
        "pm25_grade": "나쁨",
        "pm10": Decimal("180.0"),
        "ozone": Decimal("0.08"),
        "weather_alert": "",
        "alert_type": None,
    },
    "평상시": {
        "temperature": Decimal("22.0"),
        "feels_like": Decimal("22.0"),
        "humidity": Decimal("60.0"),
        "wind_speed": Decimal("3.0"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("18.0"),
        "pm25_grade": "보통",
        "pm10": Decimal("35.0"),
        "ozone": Decimal("0.04"),
        "weather_alert": "",
        "alert_type": None,
    },
}


class Command(BaseCommand):
    help = "5개 기상 시나리오 (폭염/한파/호우/미세먼지/평상시) 시드 데이터 생성"

    def add_arguments(self, parser):
        parser.add_argument(
            "--scenario",
            type=str,
            default="평상시",
            choices=list(SCENARIOS.keys()),
            help="활성화할 시나리오 (기본값: 평상시)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="기존 기상 데이터 삭제 후 생성",
        )

    def handle(self, *args, **options):
        scenario_name: str = options["scenario"]
        clear: bool = options["clear"]

        if clear:
            WeatherObservation.objects.all().delete()
            WeatherForecast.objects.all().delete()
            WeatherAlert.objects.all().delete()
            self.stdout.write("기존 기상 데이터 삭제 완료")

        now = timezone.now()
        scenario = SCENARIOS[scenario_name]

        # 최근 24시간 관측 데이터 (30분 간격, 48건)
        observations: list[WeatherObservation] = []
        for i in range(48):
            observed_at = now - timedelta(minutes=30 * (47 - i))
            temp_variation = Decimal(
                str(round(float(scenario["temperature"]) + (i % 5 - 2) * 0.5, 1))
            )
            observations.append(
                WeatherObservation(
                    observed_at=observed_at,
                    temperature=temp_variation,
                    feels_like=scenario["feels_like"],
                    humidity=scenario["humidity"],
                    wind_speed=scenario["wind_speed"],
                    precipitation=scenario["precipitation"],
                    pm25=scenario["pm25"],
                    pm25_grade=scenario["pm25_grade"],
                    pm10=scenario["pm10"],
                    ozone=scenario["ozone"],
                    weather_alert=scenario["weather_alert"],
                )
            )
        WeatherObservation.objects.bulk_create(observations)
        self.stdout.write(f"관측 데이터 {len(observations)}건 생성")

        # 72시간 예보 (3시간 간격, 24건)
        forecasts: list[WeatherForecast] = []
        base_temp = float(scenario["temperature"])
        for i in range(24):
            forecast_at = now + timedelta(hours=3 * i)
            temp_forecast = Decimal(str(round(base_temp + (i % 8 - 4) * 0.8, 1)))
            forecasts.append(
                WeatherForecast(
                    forecast_at=forecast_at,
                    temperature=temp_forecast,
                    humidity=scenario["humidity"],
                    precipitation_prob=80 if scenario_name == "호우" else 10,
                    sky_condition=(
                        "흐림" if scenario_name in ("호우", "미세먼지") else "맑음"
                    ),
                )
            )
        WeatherForecast.objects.bulk_create(forecasts)
        self.stdout.write(f"예보 데이터 {len(forecasts)}건 생성")

        # 기상특보
        alert_type = scenario.get("alert_type")
        if alert_type:
            WeatherAlert.objects.create(
                alert_type=alert_type,
                region="충남 청양군",
                issued_at=now - timedelta(hours=2),
                effective_until=now + timedelta(hours=24),
            )
            self.stdout.write(f"기상특보 생성: {alert_type}")

        self.stdout.write(
            self.style.SUCCESS(f"'{scenario_name}' 시나리오 시드 데이터 생성 완료!")
        )
