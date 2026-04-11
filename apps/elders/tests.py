"""대상자 앱 테스트 — CRUD + 필터 + 페이지네이션 + 소프트삭제"""

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.elders.models import CareWorker, Elder
from apps.risk.models import RiskScore


class ElderModelTest(TestCase):
    """Elder 모델 테스트"""

    def setUp(self):
        self.elder = Elder.objects.create(
            name="김영수",
            age=78,
            gender="M",
            address="충남 청양군 청양읍 테스트리 1번지",
            lat=Decimal("36.4592000"),
            lng=Decimal("126.8022000"),
            region_code="CY01",
            diseases=["고혈압", "당뇨"],
            disease_count=2,
            bmi=Decimal("24.5"),
            health_grade="주의",
            housing_type="단독주택",
            building_year=1990,
            has_cooling=False,
            has_heating=True,
            lives_alone=True,
            has_guardian=True,
            guardian_phone="010-1234-5678",
            care_visit_freq="주1회",
            isolation_score=Decimal("80.00"),
        )

    def test_to_risk_profile_fields(self):
        """to_risk_profile()이 필수 필드를 모두 반환하는지 확인"""
        profile = self.elder.to_risk_profile()
        required_keys = {
            "elder_id",
            "age",
            "gender",
            "diseases",
            "disease_count",
            "bmi",
            "health_grade",
            "recent_hospital",
            "housing_type",
            "building_year",
            "has_cooling",
            "has_heating",
            "flood_risk",
            "lives_alone",
            "has_guardian",
            "care_visit_freq",
            "isolation_score",
            "last_contact",
        }
        self.assertTrue(required_keys.issubset(profile.keys()))

    def test_to_risk_profile_values(self):
        """to_risk_profile() 값 변환 정확성"""
        profile = self.elder.to_risk_profile()
        self.assertEqual(profile["elder_id"], self.elder.pk)
        self.assertEqual(profile["diseases"], ["고혈압", "당뇨"])
        self.assertEqual(profile["disease_count"], 2)
        self.assertAlmostEqual(profile["bmi"], 24.5)
        self.assertEqual(profile["isolation_score"], 80.0)

    def test_str(self):
        self.assertEqual(str(self.elder), "김영수 (78세)")


class ElderAPITest(TestCase):
    """대상자 CRUD API 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.care_worker = CareWorker.objects.create(
            name="돌봄관리사1",
            phone="010-0000-0000",
            region="청양읍",
        )
        self.elder_data = {
            "name": "박순이",
            "age": 82,
            "gender": "F",
            "address": "충남 청양군 청양읍 테스트리 100번지",
            "lat": "36.4592000",
            "lng": "126.8022000",
            "diseases": ["고혈압"],
            "health_grade": "주의",
            "housing_type": "단독주택",
            "has_cooling": False,
            "has_heating": True,
            "lives_alone": True,
            "has_guardian": False,
            "care_visit_freq": "주1회",
        }

    def test_create_elder(self):
        """POST /api/elders/ — 대상자 생성"""
        resp = self.client.post("/api/elders/", self.elder_data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        elder = Elder.objects.get(name="박순이")
        self.assertEqual(elder.disease_count, 1)
        self.assertEqual(elder.region_code, "CY01")
        self.assertGreater(elder.isolation_score, 0)

    def test_create_elder_age_validation(self):
        """나이 60세 미만 검증"""
        data = {**self.elder_data, "age": 55}
        resp = self.client.post("/api/elders/", data, format="json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_list_elders(self):
        """GET /api/elders/ — 대상자 목록"""
        Elder.objects.create(
            name="테스트1", age=70, gender="M", address="테스트", region_code="CY01"
        )
        Elder.objects.create(
            name="테스트2", age=75, gender="F", address="테스트", region_code="CY02"
        )
        resp = self.client.get("/api/elders/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["count"], 2)

    def test_retrieve_elder(self):
        """GET /api/elders/{id}/ — 대상자 상세"""
        elder = Elder.objects.create(
            name="조회용", age=70, gender="M", address="테스트", region_code="CY01"
        )
        resp = self.client.get(f"/api/elders/{elder.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["name"], "조회용")

    def test_partial_update_elder(self):
        """PATCH /api/elders/{id}/ — 대상자 수정"""
        elder = Elder.objects.create(
            name="수정용", age=70, gender="M", address="테스트", region_code="CY01"
        )
        resp = self.client.patch(
            f"/api/elders/{elder.pk}/",
            {"health_grade": "위험"},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        elder.refresh_from_db()
        self.assertEqual(elder.health_grade, "위험")

    def test_update_diseases_recalculates_count(self):
        """diseases 수정 시 disease_count 자동 갱신"""
        elder = Elder.objects.create(
            name="질환수정",
            age=70,
            gender="M",
            address="테스트",
            diseases=["고혈압"],
            disease_count=1,
        )
        resp = self.client.patch(
            f"/api/elders/{elder.pk}/",
            {"diseases": ["고혈압", "당뇨", "관절염"]},
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        elder.refresh_from_db()
        self.assertEqual(elder.disease_count, 3)

    def test_soft_delete(self):
        """DELETE /api/elders/{id}/ — 소프트 삭제"""
        elder = Elder.objects.create(
            name="삭제용", age=70, gender="M", address="테스트"
        )
        resp = self.client.delete(f"/api/elders/{elder.pk}/")
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)
        elder.refresh_from_db()
        self.assertTrue(elder.is_deleted)

    def test_soft_deleted_not_in_list(self):
        """소프트 삭제된 대상자는 목록에 미노출"""
        Elder.objects.create(name="활성", age=70, gender="M", address="테스트")
        Elder.objects.create(
            name="삭제됨", age=75, gender="F", address="테스트", is_deleted=True
        )
        resp = self.client.get("/api/elders/")
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["name"], "활성")


class ElderFilterTest(TestCase):
    """대상자 필터 테스트"""

    def setUp(self):
        self.client = APIClient()
        self.e1 = Elder.objects.create(
            name="고혈압환자",
            age=70,
            gender="M",
            address="테스트",
            region_code="CY01",
            diseases=["고혈압"],
        )
        self.e2 = Elder.objects.create(
            name="당뇨환자",
            age=80,
            gender="F",
            address="테스트",
            region_code="CY02",
            diseases=["당뇨"],
        )
        self.e3 = Elder.objects.create(
            name="복합환자",
            age=75,
            gender="M",
            address="테스트",
            region_code="CY01",
            diseases=["고혈압", "당뇨"],
        )

    def test_filter_by_region(self):
        """region 필터 (startswith)"""
        resp = self.client.get("/api/elders/", {"region": "CY01"})
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_disease(self):
        """disease 필터 (JSONField contains) — PostgreSQL 전용"""
        from django.db import connection

        if connection.vendor == "sqlite":
            self.skipTest("SQLite does not support JSONField contains lookup")
        resp = self.client.get("/api/elders/", {"disease": "당뇨"})
        self.assertEqual(resp.data["count"], 2)

    def test_filter_by_level(self):
        """level 필터 (최신 RiskScore 기준)"""
        RiskScore.objects.create(
            elder=self.e1,
            total_score=75,
            risk_level="심각",
            weather_risk=30,
            health_risk=30,
            housing_risk=10,
            isolation_risk=5,
        )
        RiskScore.objects.create(
            elder=self.e2,
            total_score=20,
            risk_level="관심",
            weather_risk=10,
            health_risk=5,
            housing_risk=3,
            isolation_risk=2,
        )
        resp = self.client.get("/api/elders/", {"level": "심각"})
        self.assertEqual(resp.data["count"], 1)
        self.assertEqual(resp.data["results"][0]["name"], "고혈압환자")


class ElderPaginationTest(TestCase):
    """페이지네이션 테스트"""

    def setUp(self):
        self.client = APIClient()
        for i in range(25):
            Elder.objects.create(
                name=f"대상자{i}", age=70 + (i % 20), gender="M", address="테스트"
            )

    def test_default_page_size(self):
        """기본 페이지 크기 20"""
        resp = self.client.get("/api/elders/")
        self.assertEqual(len(resp.data["results"]), 20)
        self.assertEqual(resp.data["count"], 25)

    def test_custom_page_size(self):
        """size 파라미터로 페이지 크기 조절"""
        resp = self.client.get("/api/elders/", {"size": 10})
        self.assertEqual(len(resp.data["results"]), 10)

    def test_page_navigation(self):
        """2페이지 조회"""
        resp = self.client.get("/api/elders/", {"page": 2})
        self.assertEqual(len(resp.data["results"]), 5)
