import django_filters

from .models import Elder
from .serializers import CHEONGYANG_REGIONS

# 지역명 → 코드 매핑 (한글 지역명으로도 필터 가능하도록)
_NAME_TO_CODE: dict[str, str] = {r["name"]: r["code"] for r in CHEONGYANG_REGIONS}


class ElderFilterSet(django_filters.FilterSet):
    """대상자 필터셋 — level(콤마구분), region(코드 or 한글명), disease(overlap)"""

    level = django_filters.CharFilter(method="filter_by_level")
    region = django_filters.CharFilter(method="filter_by_region")
    region_code = django_filters.CharFilter(method="filter_by_region")
    disease = django_filters.CharFilter(method="filter_by_disease")

    class Meta:
        model = Elder
        fields: list[str] = []

    def filter_by_level(self, queryset, name: str, value: str):  # noqa: ARG002
        """콤마 구분 등급으로 필터 (최신 RiskScore의 risk_level)"""
        from django.db.models import OuterRef, Subquery

        from apps.risk.models import RiskScore

        levels = [v.strip() for v in value.split(",") if v.strip()]
        if not levels:
            return queryset

        latest_level = Subquery(
            RiskScore.objects.filter(elder=OuterRef("pk"))
            .order_by("-scored_at")
            .values("risk_level")[:1]
        )
        return queryset.annotate(current_level=latest_level).filter(
            current_level__in=levels
        )

    def filter_by_region(self, queryset, name: str, value: str):  # noqa: ARG002
        """지역 코드(CY01) 또는 한글명(청양읍) 모두 지원"""
        code = _NAME_TO_CODE.get(value, value)  # 한글이면 코드로 변환, 아니면 그대로
        return queryset.filter(region_code__startswith=code)

    def filter_by_disease(self, queryset, name: str, value: str):  # noqa: ARG002
        """질환명으로 JSONField 포함(contains) 필터"""
        return queryset.filter(diseases__contains=[value])
