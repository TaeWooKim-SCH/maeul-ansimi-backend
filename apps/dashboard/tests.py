"""대시보드 앱 테스트 — overview 집계, charts 기간별 데이터"""

from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import WeatherObservation


def _create_elder(name: str = "테스트", **kwargs) -> Elder:
    defaults = {
        "name": name,
        "age": 78,
        "gender": "M",
        "address": "충남 청양군 청양읍",
        "region_code": "CY01",
        "lives_alone": True,
    }
    defaults.update(kwargs)
    return Elder.objects.create(**defaults)


class DashboardOverviewTest(TestCase):
    """GET /api/dashboard/overview/ 테스트"""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def test_overview_empty(self):
        """데이터 없을 때"""
        resp = self.client.get("/api/dashboard/overview/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total_elders"], 0)

    def test_overview_with_data(self):
        """대상자 + 위험도 + 알림 + 기상"""
        e1 = _create_elder("위험자")
        e2 = _create_elder("안전자")

        s1 = RiskScore.objects.create(
            elder=e1,
            total_score=75,
            risk_level="심각",
            weather_risk=30,
            health_risk=25,
            housing_risk=10,
            isolation_risk=10,
        )
        RiskScore.objects.create(
            elder=e2,
            total_score=15,
            risk_level="관심",
            weather_risk=5,
            health_risk=5,
            housing_risk=3,
            isolation_risk=2,
        )

        Alert.objects.create(
            elder=e1,
            risk_score=s1,
            alert_type="긴급출동",
            alert_level="심각",
            status="발송됨",
        )

        WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("33.0"),
            feels_like=Decimal("38.0"),
            humidity=Decimal("70.0"),
            precipitation=Decimal("0"),
        )

        resp = self.client.get("/api/dashboard/overview/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["total_elders"], 2)
        self.assertEqual(resp.data["risk_counts"]["심각"], 1)
        self.assertEqual(resp.data["risk_counts"]["관심"], 1)
        self.assertEqual(resp.data["today_alerts"], 1)
        self.assertIn("weather_summary", resp.data)
        self.assertIsNotNone(resp.data["last_risk_calc"])

    def test_overview_response_rate(self):
        """응답률 계산"""
        elder = _create_elder()
        score = RiskScore.objects.create(
            elder=elder,
            total_score=55,
            risk_level="경계",
            weather_risk=20,
            health_risk=20,
            housing_risk=10,
            isolation_risk=5,
        )
        Alert.objects.create(
            elder=elder,
            risk_score=score,
            alert_type="안부전화",
            alert_level="주의",
            status="응답완료",
        )
        Alert.objects.create(
            elder=elder,
            risk_score=score,
            alert_type="방문배정",
            alert_level="경계",
            status="응답완료",
        )
        Alert.objects.create(
            elder=elder,
            risk_score=score,
            alert_type="긴급출동",
            alert_level="심각",
            status="발송됨",
        )

        resp = self.client.get("/api/dashboard/overview/")
        self.assertAlmostEqual(resp.data["response_rate"], 66.7, places=1)


class DashboardChartsTest(TestCase):
    """GET /api/dashboard/charts/ 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.elder = _create_elder()

    def test_charts_default_period(self):
        """기본 24h 기간"""
        RiskScore.objects.create(
            elder=self.elder,
            total_score=40,
            risk_level="주의",
            weather_risk=15,
            health_risk=15,
            housing_risk=5,
            isolation_risk=5,
        )
        WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("25.0"),
            precipitation=Decimal("0"),
        )

        resp = self.client.get("/api/dashboard/charts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["period"], "24h")
        self.assertGreater(len(resp.data["data"]), 0)

    def test_charts_7d_period(self):
        """7일 기간"""
        resp = self.client.get("/api/dashboard/charts/", {"period": "7d"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["period"], "7d")

    def test_charts_includes_temperature(self):
        """기온 시계열 포함"""
        WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("30.0"),
            precipitation=Decimal("0"),
        )
        resp = self.client.get("/api/dashboard/charts/")
        data_points = resp.data["data"]
        has_temp = any("temperature" in p for p in data_points)
        self.assertTrue(has_temp)
