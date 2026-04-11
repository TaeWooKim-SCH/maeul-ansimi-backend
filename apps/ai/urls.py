from django.urls import path

from .views import CalculateRiskView, FeatureImportanceView, ModelInfoView

app_name = "ai"

urlpatterns: list = [
    path("calculate-risk/", CalculateRiskView.as_view(), name="calculate-risk"),
    path(
        "feature-importance/<int:elder_id>/",
        FeatureImportanceView.as_view(),
        name="feature-importance",
    ),
    path("model-info/", ModelInfoView.as_view(), name="model-info"),
]
