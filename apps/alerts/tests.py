"""알림 앱 테스트 — 생성, 응답 처리, last_contact 갱신, 통계"""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from apps.alerts.models import Alert
from apps.elders.models import Elder
from apps.risk.models import RiskScore


def _create_elder(**kwargs) -> Elder:
    defaults = {
        "name": "테스트",
        "age": 78,
        "gender": "M",
        "address": "충남 청양군 청양읍",
        "region_code": "CY01",
        "diseases": ["고혈압"],
        "disease_count": 1,
        "lives_alone": True,
        "has_guardian": True,
        "guardian_phone": "010-1234-5678",
        "isolation_score": Decimal("60.00"),
    }
    defaults.update(kwargs)
    return Elder.objects.create(**defaults)


class AlertModelTest(TestCase):
    """Alert 모델 테스트"""

    def test_create_alert(self):
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
        alert = Alert.objects.create(
            elder=elder,
            risk_score=score,
            alert_type="방문배정",
            alert_level="경계",
            status="발송됨",
        )
        self.assertEqual(alert.status, "발송됨")
        self.assertEqual(str(alert), "테스트 - 방문배정 (발송됨)")


class AlertAPITest(TestCase):
    """알림 API 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.elder = _create_elder()
        self.score = RiskScore.objects.create(
            elder=self.elder,
            total_score=55,
            risk_level="경계",
            weather_risk=20,
            health_risk=20,
            housing_risk=10,
            isolation_risk=5,
        )
        self.alert = Alert.objects.create(
            elder=self.elder,
            risk_score=self.score,
            alert_type="방문배정",
            alert_level="경계",
            status="발송됨",
        )

    def test_list_alerts(self):
        """GET /api/alerts/"""
        resp = self.client.get("/api/alerts/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 1)

    def test_filter_by_type(self):
        """type 필터"""
        resp = self.client.get("/api/alerts/", {"type": "방문배정"})
        self.assertEqual(resp.data["count"], 1)

        resp = self.client.get("/api/alerts/", {"type": "긴급출동"})
        self.assertEqual(resp.data["count"], 0)

    def test_filter_by_status(self):
        """status 필터"""
        resp = self.client.get("/api/alerts/", {"status": "발송됨"})
        self.assertEqual(resp.data["count"], 1)

        resp = self.client.get("/api/alerts/", {"status": "응답완료"})
        self.assertEqual(resp.data["count"], 0)

    def test_filter_by_elder_id(self):
        """elder_id 필터"""
        resp = self.client.get("/api/alerts/", {"elder_id": self.elder.pk})
        self.assertEqual(resp.data["count"], 1)

    def test_respond_alert(self):
        """POST /api/alerts/{id}/respond/ — 응답 처리"""
        resp = self.client.post(
            f"/api/alerts/{self.alert.pk}/respond/",
            {"status": "응답완료", "note": "전화 확인 완료"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, "응답완료")
        self.assertEqual(self.alert.note, "전화 확인 완료")
        self.assertIsNotNone(self.alert.responded_at)

    def test_respond_updates_last_contact(self):
        """응답 시 Elder.last_contact 갱신"""
        self.assertIsNone(self.elder.last_contact)
        self.client.post(
            f"/api/alerts/{self.alert.pk}/respond/",
            {"status": "응답완료"},
            format="json",
        )
        self.elder.refresh_from_db()
        self.assertIsNotNone(self.elder.last_contact)

    def test_respond_invalid_alert(self):
        """존재하지 않는 알림"""
        resp = self.client.post(
            "/api/alerts/99999/respond/",
            {"status": "응답완료"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class AlertStatsTest(TestCase):
    """알림 통계 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.elder = _create_elder()

    def test_stats_empty(self):
        """알림 없을 때 통계"""
        resp = self.client.get("/api/alerts/stats/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["today"]["total"], 0)
        self.assertEqual(resp.data["today"]["response_rate"], 0.0)

    def test_stats_with_data(self):
        """알림 있을 때 통계 (today/week)"""
        score = RiskScore.objects.create(
            elder=self.elder,
            total_score=55,
            risk_level="경계",
            weather_risk=20,
            health_risk=20,
            housing_risk=10,
            isolation_risk=5,
        )
        Alert.objects.create(
            elder=self.elder,
            risk_score=score,
            alert_type="안부전화",
            alert_level="주의",
            status="응답완료",
        )
        Alert.objects.create(
            elder=self.elder,
            risk_score=score,
            alert_type="방문배정",
            alert_level="경계",
            status="발송됨",
        )

        resp = self.client.get("/api/alerts/stats/")
        self.assertEqual(resp.data["today"]["total"], 2)
        self.assertEqual(resp.data["today"]["responded"], 1)
        self.assertEqual(resp.data["today"]["unresponded"], 1)
        self.assertEqual(resp.data["today"]["response_rate"], 50.0)
