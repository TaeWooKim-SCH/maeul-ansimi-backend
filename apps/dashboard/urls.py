from django.urls import path

from .views import DashboardChartsView, DashboardOverviewView, RecentAlertsView

app_name = "dashboard"

urlpatterns: list = [
    path("overview/", DashboardOverviewView.as_view(), name="overview"),
    path("charts/", DashboardChartsView.as_view(), name="charts"),
    path("recent-alerts/", RecentAlertsView.as_view(), name="recent-alerts"),
]
