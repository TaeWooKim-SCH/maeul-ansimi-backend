from rest_framework import serializers

from .models import RiskScore


class RiskScoreSerializer(serializers.ModelSerializer):
    elder_name = serializers.CharField(source="elder.name", read_only=True)

    class Meta:
        model = RiskScore
        fields = (
            "id",
            "elder_id",
            "elder_name",
            "total_score",
            "risk_level",
            "weather_risk",
            "health_risk",
            "housing_risk",
            "isolation_risk",
            "scored_at",
            "model_version",
            "feature_importance",
        )


class CurrentRiskListSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField()
    total_score = serializers.DecimalField(
        source="latest_total_score", max_digits=5, decimal_places=2
    )
    risk_level = serializers.CharField(source="latest_risk_level")
    scored_at = serializers.DateTimeField(source="latest_scored_at")


class HeatmapSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField()
    age = serializers.IntegerField()
    lat = serializers.DecimalField(max_digits=10, decimal_places=7)
    lng = serializers.DecimalField(max_digits=10, decimal_places=7)
    total_score = serializers.DecimalField(
        source="latest_total_score", max_digits=5, decimal_places=2
    )
    risk_level = serializers.CharField(source="latest_risk_level")
