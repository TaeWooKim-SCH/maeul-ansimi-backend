from django.urls import path

from .views import AlertListView, AlertStatsView, respond_alert

app_name = "alerts"

urlpatterns: list = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("<int:alert_id>/respond/", respond_alert, name="alert-respond"),
    path("stats/", AlertStatsView.as_view(), name="alert-stats"),
]
