from rest_framework import serializers

from .models import WeatherAlert, WeatherForecast, WeatherObservation


class WeatherObservationSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherObservation
        exclude = ("created_at",)


class WeatherAlertSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherAlert
        exclude = ("created_at",)


class WeatherForecastSerializer(serializers.ModelSerializer):
    class Meta:
        model = WeatherForecast
        exclude = ("created_at",)


class WeatherCurrentSerializer(serializers.Serializer):
    """최신 관측 + 활성 특보 합성 응답"""

    observation = WeatherObservationSerializer()
    active_alerts = WeatherAlertSerializer(many=True)


class AirQualitySerializer(serializers.Serializer):
    pm25 = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    pm25_grade = serializers.CharField()
    pm10 = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    ozone = serializers.DecimalField(max_digits=6, decimal_places=4, allow_null=True)
    ozone_grade = serializers.CharField()
    observed_at = serializers.DateTimeField()
