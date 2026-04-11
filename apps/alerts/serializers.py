from rest_framework import serializers

from .models import Alert


class AlertSerializer(serializers.ModelSerializer):
    elder_name = serializers.CharField(source="elder.name", read_only=True)

    class Meta:
        model = Alert
        fields = (
            "id",
            "elder_id",
            "elder_name",
            "risk_score_id",
            "alert_type",
            "alert_level",
            "status",
            "note",
            "sent_at",
            "responded_at",
            "created_at",
        )


class AlertRespondSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["응답완료", "미응답"])
    note = serializers.CharField(required=False, allow_blank=True, default="")
