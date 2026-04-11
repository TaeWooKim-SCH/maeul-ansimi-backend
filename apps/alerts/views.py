from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import generics
from rest_framework import serializers as s
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .filters import AlertFilterSet
from .models import Alert
from .serializers import AlertRespondSerializer, AlertSerializer


@extend_schema(tags=["알림"])
class AlertListView(generics.ListAPIView):
    """GET /api/alerts/ — 알림 이력 목록"""

    serializer_class = AlertSerializer
    filterset_class = AlertFilterSet

    def get_queryset(self):
        return Alert.objects.select_related("elder").order_by("-created_at")


@extend_schema(tags=["알림"], request=AlertRespondSerializer, responses=AlertSerializer)
@api_view(["POST"])
def respond_alert(request: Request, alert_id: int) -> Response:
    """POST /api/alerts/{id}/respond/ — 알림 응답 처리"""
    alert = get_object_or_404(Alert, pk=alert_id)
    serializer = AlertRespondSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    alert.status = serializer.validated_data["status"]
    note = serializer.validated_data.get("note", "")
    if note:
        alert.note = note
    alert.responded_at = timezone.now()
    alert.save(update_fields=["status", "note", "responded_at"])

    # Elder.last_contact 갱신
    elder = alert.elder
    elder.last_contact = timezone.now()
    elder.save(update_fields=["last_contact"])

    return Response(AlertSerializer(alert).data)


_alert_stats_fields = {
    "total": s.IntegerField(),
    "responded": s.IntegerField(),
    "unresponded": s.IntegerField(),
    "response_rate": s.FloatField(),
}


class AlertStatsView(generics.GenericAPIView):
    """GET /api/alerts/stats/ — 알림 통계"""

    serializer_class = AlertSerializer  # schema hint

    @extend_schema(
        tags=["알림"],
        responses=inline_serializer(
            name="AlertStats",
            fields={
                "today": inline_serializer(
                    name="AlertStatsPeriod", fields=_alert_stats_fields
                ),
                "week": s.DictField(),
            },
        ),
    )
    def get(self, request: Request) -> Response:
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)

        def _calc_stats(qs) -> dict:
            total = qs.count()
            responded = qs.filter(status="응답완료").count()
            unresponded = qs.filter(status__in=["발송됨", "미응답"]).count()
            rate = round(responded / total * 100, 1) if total > 0 else 0.0
            return {
                "total": total,
                "responded": responded,
                "unresponded": unresponded,
                "response_rate": rate,
            }

        today_qs = Alert.objects.filter(created_at__gte=today_start)
        week_qs = Alert.objects.filter(created_at__gte=week_start)

        return Response(
            {
                "today": _calc_stats(today_qs),
                "week": _calc_stats(week_qs),
            }
        )
