from django.db import models


class CareWorker(models.Model):
    """돌봄관리사"""

    name: str = models.CharField("이름", max_length=50)
    phone: str = models.CharField("연락처", max_length=20)
    region: str = models.CharField("담당 지역", max_length=100)
    is_active: bool = models.BooleanField("활성 여부", default=True)

    class Meta:
        db_table = "care_workers"
        verbose_name = "돌봄관리사"
        verbose_name_plural = "돌봄관리사"

    def __str__(self) -> str:
        return f"{self.name} ({self.region})"


class Elder(models.Model):
    """돌봄 대상 고령 독거노인"""

    GENDER_CHOICES = [
        ("M", "남성"),
        ("F", "여성"),
    ]
    HEALTH_GRADE_CHOICES = [
        ("양호", "양호"),
        ("주의", "주의"),
        ("위험", "위험"),
    ]
    HOUSING_TYPE_CHOICES = [
        ("아파트", "아파트"),
        ("단독주택", "단독주택"),
        ("다세대", "다세대"),
        ("연립", "연립"),
        ("기타", "기타"),
    ]

    # 기본 정보
    name: str = models.CharField("이름", max_length=50)
    age: int = models.IntegerField("나이")
    gender: str = models.CharField("성별", max_length=1, choices=GENDER_CHOICES)
    address: str = models.TextField("주소")
    lat = models.DecimalField(
        "위도", max_digits=10, decimal_places=7, null=True, blank=True
    )
    lng = models.DecimalField(
        "경도", max_digits=10, decimal_places=7, null=True, blank=True
    )
    region_code: str = models.CharField(
        "지역코드", max_length=20, db_index=True, blank=True, default=""
    )

    # 건강 정보
    diseases = models.JSONField("질환 목록", default=list, blank=True)
    disease_count: int = models.IntegerField("질환 수", default=0)
    bmi = models.DecimalField(
        "BMI", max_digits=4, decimal_places=1, null=True, blank=True
    )
    health_grade: str = models.CharField(
        "건강등급", max_length=10, choices=HEALTH_GRADE_CHOICES, default="양호"
    )
    medications = models.JSONField("복용약 목록", default=list, blank=True)
    recent_hospital: bool = models.BooleanField("최근 입원 여부", default=False)

    # 주거 정보
    housing_type: str = models.CharField(
        "주택유형", max_length=20, choices=HOUSING_TYPE_CHOICES, default="단독주택"
    )
    building_year: int = models.IntegerField("건축년도", null=True, blank=True)
    has_cooling: bool = models.BooleanField("냉방장치", default=False)
    has_heating: bool = models.BooleanField("난방장치", default=True)
    flood_risk: bool = models.BooleanField("침수위험지역", default=False)

    # 사회적 정보
    lives_alone: bool = models.BooleanField("독거 여부", default=True)
    has_guardian: bool = models.BooleanField("보호자 유무", default=False)
    guardian_phone: str = models.CharField(
        "보호자 연락처", max_length=20, blank=True, default=""
    )
    care_visit_freq: str = models.CharField(
        "돌봄 방문 주기", max_length=20, default="주1회", blank=True
    )
    care_worker = models.ForeignKey(
        CareWorker,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="elders",
        verbose_name="담당 돌봄관리사",
    )
    isolation_score = models.DecimalField(
        "고립도 점수", max_digits=5, decimal_places=2, default=0
    )
    last_contact = models.DateTimeField("마지막 연락일", null=True, blank=True)

    # 메타
    is_deleted: bool = models.BooleanField("삭제 여부", default=False)
    created_at = models.DateTimeField("생성일", auto_now_add=True)
    updated_at = models.DateTimeField("수정일", auto_now=True)

    class Meta:
        db_table = "elders"
        verbose_name = "대상자"
        verbose_name_plural = "대상자"
        indexes = [
            models.Index(fields=["region_code"], name="idx_elder_region"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.age}세)"

    def to_risk_profile(self) -> dict:
        """AI 엔진 입력용 프로필 dict 변환"""
        return {
            "elder_id": self.pk,
            "age": self.age,
            "gender": self.gender,
            "diseases": self.diseases,
            "disease_count": self.disease_count,
            "bmi": float(self.bmi) if self.bmi else None,
            "health_grade": self.health_grade,
            "medications": self.medications,
            "recent_hospital": self.recent_hospital,
            "housing_type": self.housing_type,
            "building_year": self.building_year,
            "has_cooling": self.has_cooling,
            "has_heating": self.has_heating,
            "flood_risk": self.flood_risk,
            "lives_alone": self.lives_alone,
            "has_guardian": self.has_guardian,
            "care_visit_freq": self.care_visit_freq,
            "isolation_score": float(self.isolation_score),
            "last_contact": (
                self.last_contact.isoformat() if self.last_contact else None
            ),
        }
