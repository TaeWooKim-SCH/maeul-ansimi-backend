from django.contrib import admin

from .models import WeatherAlert, WeatherForecast, WeatherObservation


@admin.register(WeatherObservation)
class WeatherObservationAdmin(admin.ModelAdmin):
    list_display = (
        "station_name",
        "observed_at",
        "temperature",
        "feels_like",
        "humidity",
        "pm25",
    )
    list_filter = ("station_name",)
    list_per_page = 30


@admin.register(WeatherForecast)
class WeatherForecastAdmin(admin.ModelAdmin):
    list_display = (
        "forecast_at",
        "temperature",
        "humidity",
        "precipitation_prob",
        "sky_condition",
    )
    list_per_page = 30


@admin.register(WeatherAlert)
class WeatherAlertAdmin(admin.ModelAdmin):
    list_display = ("alert_type", "region", "issued_at", "effective_until")
    list_filter = ("alert_type", "region")
    list_per_page = 30
