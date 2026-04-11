"""시연 데모 스크립트 — 시나리오별 기상 주입 → 위험도 재계산 → 알림 자동생성"""

import time
from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.alerts.models import Alert
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import (WeatherAlert, WeatherForecast,
                                 WeatherObservation)

DEMO_SCENARIOS: dict[str, dict] = {
    "폭염": {
        "description": "체감온도 38℃ 폭염경보 — 심부전/COPD + 냉방없음 대상자 심각 등급",
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
        "description": "체감온도 -23℃ 한파경보 — 고혈압/심뇌혈관 대상자 위험 상승",
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
        "description": "시간당 85mm 호우경보 — 침수이력 지역 대상자 위험 상승",
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
        "description": "PM2.5 120μg/m³ — COPD/천식 대상자 경계 등급",
        "temperature": Decimal("18.0"),
        "feels_like": Decimal("18.0"),
        "humidity": Decimal("55.0"),
        "wind_speed": Decimal("2.0"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("120.0"),
        "pm25_grade": "매우나쁨",
        "pm10": Decimal("180.0"),
        "ozone": Decimal("0.08"),
        "weather_alert": "",
        "alert_type": None,
    },
}


class Command(BaseCommand):
    help = "시연 데모: 시나리오별 기상 주입 → 위험도 재계산 → 알림 자동생성"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "scenario",
            type=str,
            choices=list(DEMO_SCENARIOS.keys()),
            help="시나리오 선택: 폭염, 한파, 호우, 미세먼지",
        )
        parser.add_argument(
            "--no-clear",
            action="store_true",
            help="기존 기상/알림 데이터 유지",
        )

    def handle(self, *args, **options) -> None:
        scenario_name: str = options["scenario"]
        no_clear: bool = options["no_clear"]
        scenario = DEMO_SCENARIOS[scenario_name]

        self.stdout.write(self.style.WARNING(f"\n{'='*60}"))
        self.stdout.write(self.style.WARNING(f"  시연 시나리오: {scenario_name}"))
        self.stdout.write(self.style.WARNING(f"  {scenario['description']}"))
        self.stdout.write(self.style.WARNING(f"{'='*60}\n"))

        # Step 1: 기존 데이터 정리
        if not no_clear:
            self._clear_data()

        # Step 2: 기상 데이터 주입
        self._inject_weather(scenario_name, scenario)

        # Step 3: 위험도 재계산 (동기 실행)
        self._calculate_risk()

        # Step 4: 알림 자동생성 (동기 실행)
        self._check_alerts()

        # Step 5: 결과 요약
        self._print_summary(scenario_name)

    def _clear_data(self) -> None:
        self.stdout.write("  [1/5] 기존 기상/알림 데이터 정리 중...")
        WeatherObservation.objects.all().delete()
        WeatherForecast.objects.all().delete()
        WeatherAlert.objects.all().delete()
        Alert.objects.all().delete()
        cache.clear()
        self.stdout.write(self.style.SUCCESS("       완료"))

    def _inject_weather(self, name: str, scenario: dict) -> None:
        self.stdout.write(f"  [2/5] '{name}' 기상 데이터 주입 중...")
        now = timezone.now()

        # 최근 24시간 관측 (30분 간격)
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

        # 72시간 예보
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
                    precipitation_prob=80 if name == "호우" else 10,
                    sky_condition="흐림" if name in ("호우", "미세먼지") else "맑음",
                )
            )
        WeatherForecast.objects.bulk_create(forecasts)

        # 기상특보
        alert_type = scenario.get("alert_type")
        if alert_type:
            WeatherAlert.objects.create(
                alert_type=alert_type,
                region="충남 청양군",
                issued_at=now - timedelta(hours=2),
                effective_until=now + timedelta(hours=24),
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"       관측 {len(observations)}건, 예보 {len(forecasts)}건"
                + (f", 특보: {alert_type}" if alert_type else "")
            )
        )

    def _calculate_risk(self) -> None:
        self.stdout.write("  [3/5] 전체 대상자 위험도 재계산 중...")
        from apps.ai.engine import RiskScoringEngine
        from apps.weather.services import build_weather_condition

        engine = RiskScoringEngine()
        latest_obs = WeatherObservation.objects.order_by("-observed_at").first()
        weather_cond = build_weather_condition(latest_obs)

        elders = Elder.objects.filter(is_deleted=False)
        scores: list[RiskScore] = []
        now = timezone.now()

        for elder in elders.iterator(chunk_size=100):
            profile = elder.to_risk_profile()
            result = engine.calculate(profile, weather_cond)
            scores.append(
                RiskScore(
                    elder=elder,
                    scored_at=now,
                    weather_risk=result["weather_risk"],
                    health_risk=result["health_risk"],
                    housing_risk=result["housing_risk"],
                    isolation_risk=result["isolation_risk"],
                    total_score=result["total_score"],
                    risk_level=result["risk_level"],
                    model_version=result["model_version"],
                    feature_importance=result["feature_importance"],
                )
            )

        RiskScore.objects.bulk_create(scores, batch_size=100)
        cache.delete("risk:heatmap")
        cache.delete("dashboard:overview")

        # 등급별 집계
        level_counts: dict[str, int] = {}
        for s_item in scores:
            level_counts[s_item.risk_level] = level_counts.get(s_item.risk_level, 0) + 1

        self.stdout.write(
            self.style.SUCCESS(f"       {len(scores)}명 계산 완료: {level_counts}")
        )

    def _check_alerts(self) -> None:
        self.stdout.write("  [4/5] 등급 상승 감지 → 알림 자동생성 중...")
        from tasks.check_alerts import check_and_create_alerts

        result = check_and_create_alerts()
        self.stdout.write(self.style.SUCCESS(f"       {result}"))

    def _print_summary(self, scenario_name: str) -> None:
        self.stdout.write(f"\n  [5/5] 시연 결과 요약")
        self.stdout.write(f"  {'─'*50}")

        # 최신 계산 시점 (1분 이내)
        cutoff = timezone.now() - timedelta(minutes=1)
        latest_scores = RiskScore.objects.filter(scored_at__gte=cutoff)

        # 위험등급 분포
        for level_code, level_name in RiskScore.RISK_LEVEL_CHOICES:
            count = latest_scores.filter(risk_level=level_code).count()
            bar = "█" * (count // 5) if count > 0 else ""
            self.stdout.write(f"    {level_name}: {count:>3}명 {bar}")

        # 알림 현황
        alerts = Alert.objects.all()
        self.stdout.write(f"\n    알림 생성: {alerts.count()}건")
        for atype in ["긴급출동", "방문배정", "안부전화", "보호자알림"]:
            cnt = alerts.filter(alert_type=atype).count()
            if cnt > 0:
                self.stdout.write(f"      - {atype}: {cnt}건")

        # 고위험 대상자 상위 5명
        top_risks = latest_scores.order_by("-total_score")[:5]

        if top_risks:
            self.stdout.write(f"\n    고위험 대상자 TOP 5:")
            for r in top_risks:
                self.stdout.write(
                    f"      {r.elder.name} ({r.elder.age}세) "
                    f"— {r.total_score}점 [{r.risk_level}]"
                )

        self.stdout.write(f"\n  {'─'*50}")
        self.stdout.write(
            self.style.SUCCESS(f"  시연 준비 완료! http://localhost:8000/api/docs/")
        )
        self.stdout.write("")
