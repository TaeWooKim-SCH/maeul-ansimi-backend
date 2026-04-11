"""기상 앱 테스트 — API 연동 mock + fallback 동작"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.weather.models import (WeatherAlert, WeatherForecast,
                                 WeatherObservation)
from apps.weather.services import (AirQualityService, WeatherService,
                                   WeatherServiceWithFallback,
                                   build_weather_condition)
from common.exceptions import ServiceUnavailableError


class WeatherServiceTest(TestCase):
    """WeatherService 단위 테스트"""

    def test_calc_feels_like_heat_index(self):
        """체감온도 — Heat Index (고온)"""
        result = WeatherService.calc_feels_like(33.0, 70.0, 2.0)
        self.assertGreater(result, 33.0)

    def test_calc_feels_like_wind_chill(self):
        """체감온도 — Wind Chill (저온)"""
        result = WeatherService.calc_feels_like(-5.0, 50.0, 8.0)
        self.assertLess(result, -5.0)

    def test_calc_feels_like_neutral(self):
        """체감온도 — 중간 온도 (기온 그대로)"""
        result = WeatherService.calc_feels_like(20.0, 60.0, 3.0)
        self.assertEqual(result, 20.0)

    @patch("apps.weather.services.requests.get")
    def test_fetch_ultra_srt_ncst(self, mock_get):
        """초단기실황 API 호출 mock"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {"category": "T1H", "obsrValue": "25.5"},
                            {"category": "REH", "obsrValue": "60"},
                            {"category": "WSD", "obsrValue": "2.5"},
                            {"category": "RN1", "obsrValue": "0"},
                        ]
                    }
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        service = WeatherService()
        result = service.fetch_ultra_srt_ncst()
        self.assertEqual(result["temperature"], 25.5)
        self.assertEqual(result["humidity"], 60.0)
        self.assertEqual(result["wind_speed"], 2.5)
        self.assertIn("feels_like", result)

    @patch("apps.weather.services.requests.get")
    def test_fetch_weather_alerts_filter_cheongyang(self, mock_get):
        """기상특보 — 청양/충남 필터링"""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "response": {
                "body": {
                    "items": {
                        "item": [
                            {"title": "폭염경보: 충남 청양군", "tmFc": "202507151200"},
                            {"title": "한파주의보: 서울", "tmFc": "202501151200"},
                        ]
                    }
                }
            }
        }
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        service = WeatherService()
        alerts = service.fetch_weather_alerts()
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["alert_type"], "폭염")


class AirQualityServiceTest(TestCase):
    """AirQualityService 등급 판정 테스트"""

    def test_pm25_grades(self):
        self.assertEqual(AirQualityService._get_grade(10, "pm25"), "좋음")
        self.assertEqual(AirQualityService._get_grade(25, "pm25"), "보통")
        self.assertEqual(AirQualityService._get_grade(50, "pm25"), "나쁨")
        self.assertEqual(AirQualityService._get_grade(100, "pm25"), "매우나쁨")

    def test_none_value(self):
        self.assertEqual(AirQualityService._get_grade(None, "pm25"), "")


class WeatherFallbackTest(TestCase):
    """WeatherServiceWithFallback — 캐시 fallback 테스트"""

    @patch("apps.weather.services.WeatherService.fetch_ultra_srt_ncst")
    @patch("django.core.cache.cache.set")
    def test_success_caches_result(self, mock_cache_set, mock_fetch):
        """API 성공 시 캐시에 저장"""
        mock_fetch.return_value = {"temperature": 25.0}
        service = WeatherServiceWithFallback()
        result = service.get_weather_observation()
        self.assertEqual(result["temperature"], 25.0)
        mock_cache_set.assert_called_once()

    @patch("apps.weather.services.WeatherService.fetch_ultra_srt_ncst")
    @patch("django.core.cache.cache.get")
    def test_failure_uses_cache(self, mock_cache_get, mock_fetch):
        """API 실패 시 캐시 fallback"""
        mock_fetch.side_effect = Exception("API 오류")
        mock_cache_get.return_value = {"temperature": 20.0}

        service = WeatherServiceWithFallback()
        result = service.get_weather_observation()
        self.assertEqual(result["temperature"], 20.0)

    @patch("apps.weather.services.WeatherService.fetch_ultra_srt_ncst")
    @patch("django.core.cache.cache.get")
    def test_failure_no_cache_raises(self, mock_cache_get, mock_fetch):
        """API 실패 + 캐시 없음 → ServiceUnavailableError"""
        mock_fetch.side_effect = Exception("API 오류")
        mock_cache_get.return_value = None

        service = WeatherServiceWithFallback()
        with self.assertRaises(ServiceUnavailableError):
            service.get_weather_observation()


class BuildWeatherConditionTest(TestCase):
    """build_weather_condition() 변환 테스트"""

    def test_converts_observation(self):
        obs = WeatherObservation.objects.create(
            observed_at=timezone.now(),
            temperature=Decimal("33.0"),
            feels_like=Decimal("38.5"),
            humidity=Decimal("70.0"),
            wind_speed=Decimal("2.0"),
            precipitation=Decimal("0"),
            pm25=Decimal("85.0"),
            pm25_grade="나쁨",
            pm10=Decimal("120.0"),
            ozone=Decimal("0.08"),
            weather_alert="폭염경보",
        )
        result = build_weather_condition(obs)
        self.assertEqual(result["temperature"], 33.0)
        self.assertEqual(result["feels_like"], 38.5)
        self.assertEqual(result["pm25"], 85.0)
        self.assertEqual(result["weather_alert"], "폭염경보")

    def test_none_observation(self):
        result = build_weather_condition(None)
        self.assertEqual(result, {})


class WeatherAPITest(TestCase):
    """기상 API 엔드포인트 테스트"""

    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.obs = WeatherObservation.objects.create(
            observed_at=now,
            temperature=Decimal("25.0"),
            feels_like=Decimal("26.0"),
            humidity=Decimal("60.0"),
            wind_speed=Decimal("3.0"),
            precipitation=Decimal("0"),
            pm25=Decimal("20.0"),
            pm25_grade="보통",
            pm10=Decimal("35.0"),
            ozone=Decimal("0.04"),
        )
        self.alert = WeatherAlert.objects.create(
            alert_type="폭염",
            region="충남 청양군",
            issued_at=now - timedelta(hours=1),
            effective_until=now + timedelta(hours=24),
        )
        self.forecast = WeatherForecast.objects.create(
            forecast_at=now + timedelta(hours=3),
            temperature=Decimal("27.0"),
            humidity=Decimal("65.0"),
            precipitation_prob=20,
            sky_condition="맑음",
        )

    def test_current_weather(self):
        """GET /api/weather/current/"""
        resp = self.client.get("/api/weather/current/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("observation", resp.data)
        self.assertIn("active_alerts", resp.data)

    def test_current_weather_no_data(self):
        """관측 데이터 없을 때 404"""
        WeatherObservation.objects.all().delete()
        resp = self.client.get("/api/weather/current/")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_forecast(self):
        """GET /api/weather/forecast/"""
        resp = self.client.get("/api/weather/forecast/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn("hourly", resp.data)
        self.assertIn("weekly", resp.data)

    def test_weather_alerts(self):
        """GET /api/weather/alerts/"""
        resp = self.client.get("/api/weather/alerts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertTrue(resp.data["has_active_alert"])
        self.assertEqual(len(resp.data["alerts"]), 1)

    def test_air_quality(self):
        """GET /api/weather/air-quality/"""
        resp = self.client.get("/api/weather/air-quality/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(float(resp.data["pm25"]), 20.0)
        self.assertEqual(resp.data["pm25_grade"], "보통")
