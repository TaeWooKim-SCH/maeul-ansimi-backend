from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import viewsets
from rest_framework.request import Request
from rest_framework.response import Response

from .filters import ElderFilterSet
from .models import Elder
from .serializers import (ElderCreateSerializer, ElderDetailSerializer,
                          ElderListSerializer)

# 건강/주거/사회 정보 필드 — 변경 감지 → 위험도 재계산 트리거
_RISK_TRIGGER_FIELDS = {
    "diseases",
    "disease_count",
    "bmi",
    "health_grade",
    "medications",
    "recent_hospital",
    "housing_type",
    "building_year",
    "has_cooling",
    "has_heating",
    "flood_risk",
    "lives_alone",
    "has_guardian",
    "care_visit_freq",
    "isolation_score",
}


@extend_schema_view(
    list=extend_schema(tags=["대상자"]),
    create=extend_schema(tags=["대상자"]),
    retrieve=extend_schema(tags=["대상자"]),
    update=extend_schema(tags=["대상자"]),
    partial_update=extend_schema(tags=["대상자"]),
    destroy=extend_schema(tags=["대상자"]),
)
class ElderViewSet(viewsets.ModelViewSet):
    """대상자 CRUD ViewSet"""

    filterset_class = ElderFilterSet
    search_fields = ("name",)
    ordering_fields = ("age", "created_at")
    ordering = ("-created_at",)

    def get_queryset(self):
        return Elder.objects.filter(is_deleted=False).select_related("care_worker")

    def get_serializer_class(self):
        if self.action == "list":
            return ElderListSerializer
        if self.action in ("create",):
            return ElderCreateSerializer
        if self.action in ("retrieve", "update", "partial_update"):
            return ElderDetailSerializer
        return ElderDetailSerializer

    def perform_update(self, serializer) -> None:
        """PATCH/PUT — 건강/주거/사회 정보 변경 감지 시 위험도 재계산 트리거"""
        instance: Elder = serializer.instance
        changed_fields = set(serializer.validated_data.keys())

        # diseases 변경 시 disease_count 자동 갱신
        if "diseases" in changed_fields:
            diseases = serializer.validated_data["diseases"]
            serializer.validated_data["disease_count"] = (
                len(diseases) if diseases else 0
            )

        elder = serializer.save()

        if changed_fields & _RISK_TRIGGER_FIELDS:
            try:
                from tasks.calculate_risk import calculate_single_risk

                calculate_single_risk.delay(elder.pk)
            except Exception:
                pass

    def destroy(self, request: Request, *args, **kwargs) -> Response:
        """소프트 삭제"""
        instance: Elder = self.get_object()
        instance.is_deleted = True
        instance.save(update_fields=["is_deleted"])
        return Response(status=204)
