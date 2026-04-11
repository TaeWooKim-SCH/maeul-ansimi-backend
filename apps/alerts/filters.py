from datetime import timedelta

import django_filters
from django.utils import timezone

from .models import Alert

PERIOD_MAP: dict[str, timedelta] = {
    "today": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


class AlertFilterSet(django_filters.FilterSet):
    elder_id = django_filters.NumberFilter(field_name="elder_id")
    type = django_filters.CharFilter(field_name="alert_type")
    status = django_filters.CharFilter(field_name="status")
    period = django_filters.CharFilter(method="filter_by_period")

    class Meta:
        model = Alert
        fields: list[str] = []

    def filter_by_period(self, queryset, name: str, value: str):  # noqa: ARG002
        delta = PERIOD_MAP.get(value)
        if delta is None:
            return queryset
        return queryset.filter(created_at__gte=timezone.now() - delta)
