from django.db import models


class RiskScore(models.Model):
    """위험도 평가 결과"""

    RISK_LEVEL_CHOICES = [
        ("관심", "관심"),
        ("주의", "주의"),
        ("경계", "경계"),
        ("심각", "심각"),
    ]

    elder = models.ForeignKey(
        "elders.Elder",
        on_delete=models.CASCADE,
        related_name="risk_scores",
        verbose_name="대상자",
    )
    scored_at = models.DateTimeField("평가 시각", auto_now_add=True)

    # 하위 점수 (0~100)
    weather_risk = models.DecimalField(
        "기상 위험도", max_digits=5, decimal_places=2, default=0
    )
    health_risk = models.DecimalField(
        "건강 위험도", max_digits=5, decimal_places=2, default=0
    )
    housing_risk = models.DecimalField(
        "주거 위험도", max_digits=5, decimal_places=2, default=0
    )
    isolation_risk = models.DecimalField(
        "고립 위험도", max_digits=5, decimal_places=2, default=0
    )
    total_score = models.DecimalField(
        "종합 점수", max_digits=5, decimal_places=2, default=0
    )

    risk_level: str = models.CharField(
        "위험 등급", max_length=10, choices=RISK_LEVEL_CHOICES, default="관심"
    )
    model_version: str = models.CharField(
        "모델 버전", max_length=20, default="rule-v1.0"
    )
    feature_importance = models.JSONField("기여도", default=dict, blank=True)

    class Meta:
        db_table = "risk_scores"
        verbose_name = "위험도 평가"
        verbose_name_plural = "위험도 평가"
        indexes = [
            models.Index(fields=["elder", "-scored_at"], name="idx_risk_elder_scored"),
            models.Index(fields=["risk_level"], name="idx_risk_level"),
        ]

    def __str__(self) -> str:
        return f"{self.elder.name} - {self.risk_level} ({self.total_score})"
