"""Celery 태스크 단위 테스트 + 통합 테스트

CELERY_TASK_ALWAYS_EAGER=True 모드로 동기 실행 테스트
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alerts.models import Alert
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import WeatherForecast, WeatherObservation


def _create_elder(**kwargs) -> Elder:
    defaults = {
        "name": "테스트",
        "age": 78,
        "gender": "M",
        "address": "충남 청양군 청양읍",
        "region_code": "CY01",
        "diseases": ["고혈압", "당뇨"],
        "disease_count": 2,
        "bmi": Decimal("24.5"),
        "health_grade": "주의",
        "housing_type": "단독주택",
        "building_year": 1985,
        "has_cooling": False,
        "has_heating": True,
        "lives_alone": True,
        "has_guardian": True,
        "guardian_phone": "010-1234-5678",
        "isolation_score": Decimal("80.00"),
    }
    defaults.update(kwargs)
    return Elder.objects.create(**defaults)


def _create_weather(**kwargs) -> WeatherObservation:
    defaults = {
        "observed_at": timezone.now(),
        "temperature": Decimal("22.0"),
        "feels_like": Decimal("22.0"),
        "humidity": Decimal("60.0"),
        "wind_speed": Decimal("3.0"),
        "precipitation": Decimal("0"),
        "pm25": Decimal("18.0"),
        "pm25_grade": "보통",
    }
    defaults.update(kwargs)
    return WeatherObservation.objects.create(**defaults)


# =============================================================================
# calculate_risk 태스크 테스트
# =============================================================================


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CalculateRiskTaskTest(TestCase):
    """위험도 계산 태스크 테스트"""

    def setUp(self):
        self.elder = _create_elder()
        self.weather = _create_weather()

    def test_calculate_single_risk(self):
        """단건 위험도 계산"""
        from tasks.calculate_risk import calculate_single_risk

        result = calculate_single_risk(self.elder.pk)
        self.assertTrue(result.startswith("ok:"))

        score = RiskScore.objects.filter(elder=self.elder).first()
        self.assertIsNotNone(score)
        self.assertIn(score.risk_level, ["관심", "주의", "경계", "심각"])
        self.assertEqual(score.model_version, "rule-v1.0")

    def test_calculate_single_risk_not_found(self):
        """존재하지 않는 대상자"""
        from tasks.calculate_risk import calculate_single_risk

        result = calculate_single_risk(99999)
        self.assertIn("elder_not_found", result)

    def test_calculate_all_risk(self):
        """전체 위험도 일괄 계산"""
        _create_elder(name="대상자2")
        _create_elder(name="대상자3")

        from tasks.calculate_risk import calculate_all_risk

        result = calculate_all_risk()
        self.assertIn("3 elders", result)

        self.assertEqual(RiskScore.objects.count(), 3)

    def test_calculate_all_risk_no_weather(self):
        """기상 데이터 없을 때도 동작"""
        WeatherObservation.objects.all().delete()

        from tasks.calculate_risk import calculate_all_risk

        result = calculate_all_risk()
        self.assertIn("1 elders", result)


# =============================================================================
# check_alerts 태스크 테스트
# =============================================================================


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CheckAlertsTaskTest(TestCase):
    """알림 자동 생성 태스크 테스트"""

    def setUp(self):
        self.elder = _create_elder()

    def test_first_evaluation_high_risk(self):
        """첫 평가 — 주의 이상이면 알림 생성"""
        RiskScore.objects.create(
            elder=self.elder,
            total_score=55,
            risk_level="경계",
            weather_risk=20,
            health_risk=20,
            housing_risk=10,
            isolation_risk=5,
        )

        from tasks.check_alerts import check_and_create_alerts

        result = check_and_create_alerts()
        self.assertIn("alerts created", result)

        alerts = Alert.objects.filter(elder=self.elder)
        self.assertTrue(alerts.exists())
        alert_types = list(alerts.values_list("alert_type", flat=True))
        self.assertIn("방문배정", alert_types)
        self.assertIn("보호자알림", alert_types)

    def test_first_evaluation_low_risk(self):
        """첫 평가 — 관심이면 알림 미생성"""
        RiskScore.objects.create(
            elder=self.elder,
            total_score=15,
            risk_level="관심",
            weather_risk=5,
            health_risk=5,
            housing_risk=3,
            isolation_risk=2,
        )

        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts()
        self.assertEqual(Alert.objects.filter(elder=self.elder).count(), 0)

    def test_level_escalation(self):
        """등급 상승 감지 → 알림 생성"""
        old = RiskScore.objects.create(
            elder=self.elder,
            total_score=25,
            risk_level="관심",
            weather_risk=10,
            health_risk=10,
            housing_risk=3,
            isolation_risk=2,
        )
        RiskScore.objects.filter(pk=old.pk).update(
            scored_at=timezone.now() - timedelta(hours=2)
        )
        RiskScore.objects.create(
            elder=self.elder,
            total_score=75,
            risk_level="심각",
            weather_risk=30,
            health_risk=25,
            housing_risk=10,
            isolation_risk=10,
        )

        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts()

        alerts = Alert.objects.filter(elder=self.elder)
        self.assertTrue(alerts.exists())
        self.assertTrue(alerts.filter(alert_type="긴급출동").exists())

    def test_no_escalation_no_alert(self):
        """등급 유지/하락 → 알림 미생성"""
        old = RiskScore.objects.create(
            elder=self.elder,
            total_score=55,
            risk_level="경계",
            weather_risk=20,
            health_risk=20,
            housing_risk=10,
            isolation_risk=5,
        )
        RiskScore.objects.filter(pk=old.pk).update(
            scored_at=timezone.now() - timedelta(hours=2)
        )
        RiskScore.objects.create(
            elder=self.elder,
            total_score=25,
            risk_level="관심",
            weather_risk=10,
            health_risk=10,
            housing_risk=3,
            isolation_risk=2,
        )

        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts()
        self.assertEqual(Alert.objects.filter(elder=self.elder).count(), 0)

    def test_guardian_alert_for_critical(self):
        """심각 등급 + 보호자 → 보호자알림 추가 생성"""
        old = RiskScore.objects.create(
            elder=self.elder,
            total_score=35,
            risk_level="주의",
            weather_risk=15,
            health_risk=10,
            housing_risk=5,
            isolation_risk=5,
        )
        RiskScore.objects.filter(pk=old.pk).update(
            scored_at=timezone.now() - timedelta(hours=2)
        )
        RiskScore.objects.create(
            elder=self.elder,
            total_score=80,
            risk_level="심각",
            weather_risk=30,
            health_risk=25,
            housing_risk=15,
            isolation_risk=10,
        )

        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts()

        guardian_alerts = Alert.objects.filter(
            elder=self.elder, alert_type="보호자알림"
        )
        self.assertTrue(guardian_alerts.exists())

    def test_no_guardian_alert_without_guardian(self):
        """보호자 없으면 보호자알림 미생성"""
        elder_no_guardian = _create_elder(
            name="무보호자", has_guardian=False, guardian_phone=""
        )
        old = RiskScore.objects.create(
            elder=elder_no_guardian,
            total_score=35,
            risk_level="주의",
            weather_risk=15,
            health_risk=10,
            housing_risk=5,
            isolation_risk=5,
        )
        RiskScore.objects.filter(pk=old.pk).update(
            scored_at=timezone.now() - timedelta(hours=2)
        )
        RiskScore.objects.create(
            elder=elder_no_guardian,
            total_score=80,
            risk_level="심각",
            weather_risk=30,
            health_risk=25,
            housing_risk=15,
            isolation_risk=10,
        )

        from tasks.check_alerts import check_and_create_alerts

        check_and_create_alerts()

        guardian_alerts = Alert.objects.filter(
            elder=elder_no_guardian, alert_type="보호자알림"
        )
        self.assertFalse(guardian_alerts.exists())


# =============================================================================
# fetch_weather 태스크 테스트
# =============================================================================


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class FetchWeatherTaskTest(TestCase):
    """기상 데이터 수집 태스크 테스트"""

    @patch("apps.weather.services.WeatherServiceWithFallback.get_weather_observation")
    def test_fetch_weather_observation(self, mock_fetch):
        """기상 관측 수집"""
        mock_fetch.return_value = {
            "observed_at": timezone.now(),
            "temperature": 25.5,
            "feels_like": 26.0,
            "humidity": 60.0,
            "wind_speed": 3.0,
            "precipitation": 0,
        }

        from tasks.fetch_weather import fetch_weather_observation

        result = fetch_weather_observation()
        self.assertIn("ok", result)
        self.assertEqual(WeatherObservation.objects.count(), 1)

    @patch("apps.weather.services.WeatherServiceWithFallback.get_weather_forecast")
    def test_fetch_weather_forecast(self, mock_fetch):
        """예보 수집"""
        now = timezone.now()
        mock_fetch.return_value = [
            {
                "forecast_at": now + timedelta(hours=3),
                "temperature": 27.0,
                "humidity": 65.0,
                "precipitation_prob": 20,
                "sky_condition": "맑음",
            },
        ]

        from tasks.fetch_weather import fetch_weather_forecast

        result = fetch_weather_forecast()
        self.assertIn("ok", result)
        self.assertEqual(WeatherForecast.objects.count(), 1)

    @patch("apps.weather.services.WeatherServiceWithFallback.get_air_quality")
    def test_fetch_air_quality(self, mock_fetch):
        """대기질 수집 → 최신 관측 업데이트"""
        obs = _create_weather()
        mock_fetch.return_value = {
            "pm25": 45.0,
            "pm25_grade": "나쁨",
            "pm10": 80.0,
            "ozone": 0.07,
        }

        from tasks.fetch_weather import fetch_air_quality

        result = fetch_air_quality()
        self.assertIn("ok", result)

        obs.refresh_from_db()
        self.assertEqual(float(obs.pm25), 45.0)
        self.assertEqual(obs.pm25_grade, "나쁨")


# =============================================================================
# cleanup 태스크 테스트
# =============================================================================


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class CleanupTaskTest(TestCase):
    """데이터 정리 태스크 테스트"""

    def test_cleanup_old_data(self):
        """30일 초과 데이터 삭제"""
        now = timezone.now()
        # 최근 데이터 (유지)
        WeatherObservation.objects.create(
            observed_at=now - timedelta(days=5),
            temperature=Decimal("22.0"),
            precipitation=Decimal("0"),
        )
        # 오래된 데이터 (삭제 대상)
        WeatherObservation.objects.create(
            observed_at=now - timedelta(days=35),
            temperature=Decimal("20.0"),
            precipitation=Decimal("0"),
        )
        WeatherObservation.objects.create(
            observed_at=now - timedelta(days=60),
            temperature=Decimal("18.0"),
            precipitation=Decimal("0"),
        )

        from tasks.cleanup import cleanup_old_data

        result = cleanup_old_data()
        self.assertIn("deleted 2", result)
        self.assertEqual(WeatherObservation.objects.count(), 1)


# =============================================================================
# 통합 테스트: 기상 수집 → 위험도 계산 → 등급 상승 → 알림 자동생성
# =============================================================================


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class IntegrationFlowTest(TestCase):
    """통합 테스트 — 전체 플로우

    기상 수집 → 위험도 계산 → 등급 상승 → 알림 자동생성
    """

    def test_full_flow_heatwave_scenario(self):
        """폭염 시나리오 전체 플로우"""
        # 1. 대상자 등록 (고위험: 심부전 환자, 냉방 없음)
        elder = _create_elder(
            name="고위험",
            diseases=["심부전", "고혈압"],
            disease_count=2,
            health_grade="위험",
            has_cooling=False,
            has_guardian=True,
            isolation_score=Decimal("85.00"),
        )

        # 2. 평상시 기상 → 초기 위험도
        normal_weather = _create_weather(
            temperature=Decimal("22.0"),
            feels_like=Decimal("22.0"),
        )

        from tasks.calculate_risk import calculate_all_risk

        calculate_all_risk()

        initial_score = RiskScore.objects.filter(elder=elder).first()
        self.assertIsNotNone(initial_score)
        initial_level = initial_score.risk_level

        # 3. 폭염 기상으로 변경
        heatwave_weather = WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("38.0"),
            feels_like=Decimal("42.0"),
            humidity=Decimal("75.0"),
            wind_speed=Decimal("1.0"),
            precipitation=Decimal("0"),
            weather_alert="폭염경보: 충남 청양군",
        )

        # 4. 위험도 재계산 (calculate_all_risk → check_and_create_alerts 체이닝)
        calculate_all_risk()

        # 5. 검증: 위험도 점수가 2건 이상
        scores = RiskScore.objects.filter(elder=elder).order_by("-id")
        self.assertGreaterEqual(scores.count(), 2)

        latest_score = scores.first()
        self.assertIn(latest_score.risk_level, ("경계", "심각"))

        # 6. 검증: 알림 자동 생성
        alerts = Alert.objects.filter(elder=elder)
        self.assertTrue(alerts.exists())

        # 주요 알림 유형 확인
        alert_types = set(alerts.values_list("alert_type", flat=True))
        # 경계 이상이면 방문배정 또는 긴급출동 + 보호자알림
        self.assertTrue(
            alert_types & {"방문배정", "긴급출동"},
            f"예상 알림 유형 누락: {alert_types}",
        )

    def test_full_flow_normal_to_warning(self):
        """평상시 → 주의 등급 상승 플로우"""
        elder = _create_elder(
            name="일반대상자",
            diseases=["고혈압"],
            disease_count=1,
            health_grade="주의",
            has_cooling=True,
            has_guardian=False,
            isolation_score=Decimal("50.00"),
        )

        # 평상시 기상
        _create_weather()

        from tasks.calculate_risk import calculate_all_risk

        calculate_all_risk()

        # 미세먼지 고농도
        WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("18.0"),
            feels_like=Decimal("18.0"),
            humidity=Decimal("55.0"),
            precipitation=Decimal("0"),
            pm25=Decimal("160.0"),
            pm25_grade="매우나쁨",
        )

        calculate_all_risk()

        scores = RiskScore.objects.filter(elder=elder).order_by("-scored_at")
        self.assertGreaterEqual(scores.count(), 2)
