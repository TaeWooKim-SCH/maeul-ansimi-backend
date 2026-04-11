"""위험도 앱 테스트 — 계산, 이력, 통계, 히트맵 캐시"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.ai.engine import RiskScoringEngine
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import WeatherObservation


def _create_elder(**kwargs) -> Elder:
    defaults = {
        "name": "테스트",
        "age": 78,
        "gender": "M",
        "address": "충남 청양군 청양읍",
        "lat": Decimal("36.4592000"),
        "lng": Decimal("126.8022000"),
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


class RiskScoringEngineTest(TestCase):
    """AI 엔진 위험도 계산 테스트"""

    def setUp(self):
        self.engine = RiskScoringEngine()

    def test_normal_conditions(self):
        """평상시 — 낮은 위험도"""
        profile = {
            "diseases": [],
            "disease_count": 0,
            "bmi": 22.0,
            "health_grade": "양호",
            "recent_hospital": False,
            "housing_type": "아파트",
            "building_year": 2010,
            "has_cooling": True,
            "has_heating": True,
            "flood_risk": False,
            "lives_alone": False,
            "has_guardian": True,
            "isolation_score": 10,
            "last_contact": "2025-01-01T10:00:00",
        }
        weather = {
            "temperature": 22.0,
            "feels_like": 22.0,
            "humidity": 60,
            "pm25": 15,
            "precipitation": 0,
            "weather_alert": None,
        }
        result = self.engine.calculate(profile, weather)
        self.assertEqual(result["risk_level"], "관심")
        self.assertLessEqual(result["total_score"], 30)
        self.assertEqual(result["model_version"], "rule-v1.0")

    def test_heatwave_high_risk(self):
        """폭염 + 심부전 환자 — 높은 위험도 + 교차위험 적용"""
        profile = {
            "diseases": ["심부전", "고혈압"],
            "disease_count": 2,
            "bmi": 28.0,
            "health_grade": "위험",
            "recent_hospital": True,
            "housing_type": "단독주택",
            "building_year": 1980,
            "has_cooling": False,
            "has_heating": True,
            "flood_risk": False,
            "lives_alone": True,
            "has_guardian": False,
            "isolation_score": 90,
            "last_contact": None,
        }
        weather = {
            "temperature": 36.0,
            "feels_like": 40.0,
            "humidity": 70,
            "pm25": 20,
            "precipitation": 0,
            "weather_alert": "폭염경보: 충남 청양군",
        }
        result = self.engine.calculate(profile, weather)
        self.assertIn(result["risk_level"], ("경계", "심각"))
        self.assertGreater(result["total_score"], 50)

    def test_cold_wave(self):
        """한파 시나리오"""
        profile = {
            "diseases": ["뇌졸중"],
            "disease_count": 1,
            "bmi": 22.0,
            "health_grade": "주의",
            "recent_hospital": False,
            "housing_type": "단독주택",
            "building_year": 1995,
            "has_cooling": False,
            "has_heating": False,
            "flood_risk": False,
            "lives_alone": True,
            "has_guardian": True,
            "isolation_score": 50,
            "last_contact": "2025-01-01T10:00:00",
        }
        weather = {
            "temperature": -15.0,
            "feels_like": -23.0,
            "humidity": 35,
            "pm25": 20,
            "precipitation": 0,
            "weather_alert": "한파경보",
        }
        result = self.engine.calculate(profile, weather)
        self.assertGreater(result["weather_risk"], 40)
        self.assertIn("temperature", result["feature_importance"])

    def test_pm25_risk(self):
        """미세먼지 나쁨"""
        profile = {
            "diseases": ["호흡기질환"],
            "disease_count": 1,
            "bmi": 22.0,
            "health_grade": "양호",
            "recent_hospital": False,
            "housing_type": "아파트",
            "building_year": 2005,
            "has_cooling": True,
            "has_heating": True,
            "flood_risk": False,
            "lives_alone": False,
            "has_guardian": True,
            "isolation_score": 10,
            "last_contact": "2025-01-01T10:00:00",
        }
        weather = {
            "temperature": 18.0,
            "feels_like": 18.0,
            "humidity": 55,
            "pm25": 120,
            "precipitation": 0,
            "weather_alert": None,
        }
        result = self.engine.calculate(profile, weather)
        self.assertIn("pm25", result["feature_importance"])

    def test_empty_weather(self):
        """기상 데이터 없는 경우"""
        profile = {
            "diseases": [],
            "disease_count": 0,
            "health_grade": "양호",
            "recent_hospital": False,
            "housing_type": "아파트",
            "building_year": 2010,
            "has_cooling": True,
            "has_heating": True,
            "flood_risk": False,
            "lives_alone": False,
            "has_guardian": True,
            "isolation_score": 10,
            "last_contact": "2025-01-01T10:00:00",
        }
        result = self.engine.calculate(profile, {})
        self.assertEqual(result["weather_risk"], 0)
        self.assertIsNotNone(result["risk_level"])

    def test_score_capped_at_100(self):
        """종합 점수 100점 상한"""
        profile = {
            "diseases": ["심부전", "고혈압", "당뇨", "뇌졸중", "호흡기질환"],
            "disease_count": 5,
            "bmi": 16.0,
            "health_grade": "위험",
            "recent_hospital": True,
            "housing_type": "단독주택",
            "building_year": 1975,
            "has_cooling": False,
            "has_heating": False,
            "flood_risk": True,
            "lives_alone": True,
            "has_guardian": False,
            "isolation_score": 100,
            "last_contact": None,
        }
        weather = {
            "temperature": 38.0,
            "feels_like": 45.0,
            "humidity": 80,
            "pm25": 200,
            "precipitation": 50,
            "weather_alert": "폭염경보",
        }
        result = self.engine.calculate(profile, weather)
        self.assertLessEqual(result["total_score"], 100)


class RiskAPITest(TestCase):
    """위험도 API 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.elder = _create_elder()
        self.weather = _create_weather()
        self.score = RiskScore.objects.create(
            elder=self.elder,
            weather_risk=Decimal("30.00"),
            health_risk=Decimal("35.00"),
            housing_risk=Decimal("25.00"),
            isolation_risk=Decimal("80.00"),
            total_score=Decimal("55.25"),
            risk_level="경계",
            feature_importance={"temperature": 30, "disease_count": 20},
            model_version="rule-v1.0",
        )

    def test_current_risk_list(self):
        """GET /api/risk/current/"""
        resp = self.client.get("/api/risk/current/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    def test_current_risk_level_filter(self):
        """GET /api/risk/current/?level=경계"""
        resp = self.client.get("/api/risk/current/", {"level": "경계"})
        self.assertEqual(len(resp.data), 1)

        resp = self.client.get("/api/risk/current/", {"level": "심각"})
        self.assertEqual(len(resp.data), 0)

    def test_elder_risk_detail(self):
        """GET /api/risk/elder/{id}/"""
        resp = self.client.get(f"/api/risk/elder/{self.elder.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["risk_level"], "경계")
        self.assertIn("recommended_action", resp.data)
        self.assertIn("top_factors", resp.data)

    def test_elder_risk_detail_not_found(self):
        """존재하지 않는 대상자"""
        resp = self.client.get("/api/risk/elder/99999/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_risk_history(self):
        """GET /api/risk/elder/{id}/history/?period=24h"""
        resp = self.client.get(f"/api/risk/elder/{self.elder.pk}/history/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["period"], "24h")
        self.assertEqual(len(resp.data["history"]), 1)

    def test_risk_history_period_filter(self):
        """기간별 이력 필터"""
        old_score = RiskScore.objects.create(
            elder=self.elder,
            weather_risk=20,
            health_risk=20,
            housing_risk=20,
            isolation_risk=20,
            total_score=20,
            risk_level="관심",
        )
        # scored_at을 8일 전으로 조작
        RiskScore.objects.filter(pk=old_score.pk).update(
            scored_at=timezone.now() - timedelta(days=8)
        )
        resp = self.client.get(
            f"/api/risk/elder/{self.elder.pk}/history/", {"period": "7d"}
        )
        self.assertEqual(len(resp.data["history"]), 1)

        resp = self.client.get(
            f"/api/risk/elder/{self.elder.pk}/history/", {"period": "30d"}
        )
        self.assertEqual(len(resp.data["history"]), 2)

    def test_risk_summary(self):
        """GET /api/risk/summary/"""
        resp = self.client.get("/api/risk/summary/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("by_level", resp.data)
        self.assertEqual(resp.data["by_level"]["경계"], 1)

    def test_heatmap(self):
        """GET /api/risk/heatmap/"""
        resp = self.client.get("/api/risk/heatmap/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data), 1)

    @patch("django.core.cache.cache.get")
    def test_heatmap_cache(self, mock_cache_get):
        """히트맵 캐시 히트 확인"""
        cached_data = [{"id": 1, "name": "캐시"}]
        mock_cache_get.return_value = cached_data

        resp = self.client.get("/api/risk/heatmap/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data, cached_data)
        mock_cache_get.assert_called_with("risk:heatmap")
