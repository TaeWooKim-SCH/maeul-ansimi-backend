from django.urls import path

from .views import (AirQualityView, CurrentWeatherView, ForecastView,
                    WeatherAlertListView)

app_name = "weather"

urlpatterns: list = [
    path("current/", CurrentWeatherView.as_view(), name="current"),
    path("forecast/", ForecastView.as_view(), name="forecast"),
    path("alerts/", WeatherAlertListView.as_view(), name="alert-list"),
    path("air-quality/", AirQualityView.as_view(), name="air-quality"),
]
