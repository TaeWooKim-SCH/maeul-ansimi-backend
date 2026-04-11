from django.db import models


class WeatherObservation(models.Model):
    """기상 실황 관측 데이터"""

    station_id: str = models.CharField("관측소 ID", max_length=10, default="238")
    station_name: str = models.CharField("관측소명", max_length=50, default="청양")
    observed_at = models.DateTimeField("관측 시각")

    temperature = models.DecimalField("기온(℃)", max_digits=5, decimal_places=1)
    feels_like = models.DecimalField(
        "체감온도(℃)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    humidity = models.DecimalField(
        "습도(%)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    wind_speed = models.DecimalField(
        "풍속(m/s)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    precipitation = models.DecimalField(
        "강수량(mm)", max_digits=7, decimal_places=1, default=0
    )

    pm25 = models.DecimalField(
        "PM2.5(㎍/㎥)", max_digits=6, decimal_places=1, null=True, blank=True
    )
    pm25_grade: str = models.CharField(
        "PM2.5 등급", max_length=10, blank=True, default=""
    )
    pm10 = models.DecimalField(
        "PM10(㎍/㎥)", max_digits=6, decimal_places=1, null=True, blank=True
    )
    ozone = models.DecimalField(
        "오존(ppm)", max_digits=6, decimal_places=4, null=True, blank=True
    )
    weather_alert: str = models.CharField(
        "기상특보", max_length=200, blank=True, default=""
    )

    created_at = models.DateTimeField("생성일", auto_now_add=True)

    class Meta:
        db_table = "weather_observations"
        verbose_name = "기상 관측"
        verbose_name_plural = "기상 관측"
        indexes = [
            models.Index(fields=["-observed_at"], name="idx_weather_obs_at"),
        ]

    def __str__(self) -> str:
        return f"{self.station_name} {self.observed_at:%Y-%m-%d %H:%M} ({self.temperature}℃)"


class WeatherForecast(models.Model):
    """기상 예보 데이터"""

    forecast_at = models.DateTimeField("예보 시각")
    temperature = models.DecimalField("예보 기온(℃)", max_digits=5, decimal_places=1)
    humidity = models.DecimalField(
        "예보 습도(%)", max_digits=5, decimal_places=1, null=True, blank=True
    )
    precipitation_prob = models.IntegerField("강수확률(%)", default=0)
    sky_condition: str = models.CharField(
        "하늘상태", max_length=20, blank=True, default=""
    )

    created_at = models.DateTimeField("생성일", auto_now_add=True)

    class Meta:
        db_table = "weather_forecasts"
        verbose_name = "기상 예보"
        verbose_name_plural = "기상 예보"

    def __str__(self) -> str:
        return f"{self.forecast_at:%Y-%m-%d %H:%M} ({self.temperature}℃)"


class WeatherAlert(models.Model):
    """기상 특보"""

    ALERT_TYPE_CHOICES = [
        ("폭염", "폭염"),
        ("한파", "한파"),
        ("호우", "호우"),
        ("강풍", "강풍"),
        ("대설", "대설"),
        ("풍랑", "풍랑"),
        ("기타", "기타"),
    ]

    alert_type: str = models.CharField(
        "특보 유형", max_length=20, choices=ALERT_TYPE_CHOICES
    )
    region: str = models.CharField("지역", max_length=100, default="충남 청양군")
    issued_at = models.DateTimeField("발효 시각")
    effective_until = models.DateTimeField("종료 시각", null=True, blank=True)

    created_at = models.DateTimeField("생성일", auto_now_add=True)

    class Meta:
        db_table = "weather_alerts"
        verbose_name = "기상 특보"
        verbose_name_plural = "기상 특보"

    def __str__(self) -> str:
        return f"{self.alert_type} - {self.region} ({self.issued_at:%Y-%m-%d})"
