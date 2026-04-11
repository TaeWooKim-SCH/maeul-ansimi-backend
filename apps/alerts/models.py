from django.db import models


class Alert(models.Model):
    """알림"""

    ALERT_TYPE_CHOICES = [
        ("안부전화", "안부전화"),
        ("방문배정", "방문배정"),
        ("긴급출동", "긴급출동"),
        ("보호자알림", "보호자알림"),
    ]
    ALERT_LEVEL_CHOICES = [
        ("주의", "주의"),
        ("경계", "경계"),
        ("심각", "심각"),
    ]
    STATUS_CHOICES = [
        ("발송됨", "발송됨"),
        ("응답완료", "응답완료"),
        ("미응답", "미응답"),
    ]

    elder = models.ForeignKey(
        "elders.Elder",
        on_delete=models.CASCADE,
        related_name="alerts",
        verbose_name="대상자",
    )
    risk_score = models.ForeignKey(
        "risk.RiskScore",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alerts",
        verbose_name="위험도 평가",
    )

    alert_type: str = models.CharField(
        "알림 유형", max_length=20, choices=ALERT_TYPE_CHOICES
    )
    alert_level: str = models.CharField(
        "알림 등급", max_length=10, choices=ALERT_LEVEL_CHOICES
    )
    status: str = models.CharField(
        "상태", max_length=10, choices=STATUS_CHOICES, default="발송됨"
    )

    note: str = models.TextField("비고", blank=True, default="")
    sent_at = models.DateTimeField("발송 시각", auto_now_add=True)
    responded_at = models.DateTimeField("응답 시각", null=True, blank=True)

    created_at = models.DateTimeField("생성일", auto_now_add=True)

    class Meta:
        db_table = "alerts"
        verbose_name = "알림"
        verbose_name_plural = "알림"
        indexes = [
            models.Index(
                fields=["elder", "-created_at"], name="idx_alert_elder_created"
            ),
            models.Index(fields=["status"], name="idx_alert_status"),
        ]

    def __str__(self) -> str:
        return f"{self.elder.name} - {self.alert_type} ({self.status})"
