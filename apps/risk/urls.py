from django.urls import path

from .views import (CurrentRiskListView, ElderRiskDetailView,
                    ElderRiskHistoryView, HeatmapView, RiskSummaryView)

app_name = "risk"

urlpatterns: list = [
    path("current/", CurrentRiskListView.as_view(), name="current-list"),
    path("elder/<int:elder_id>/", ElderRiskDetailView.as_view(), name="elder-detail"),
    path(
        "elder/<int:elder_id>/history/",
        ElderRiskHistoryView.as_view(),
        name="elder-history",
    ),
    path("summary/", RiskSummaryView.as_view(), name="summary"),
    path("heatmap/", HeatmapView.as_view(), name="heatmap"),
]
