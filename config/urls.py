from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (SpectacularAPIView, SpectacularRedocView,
                                   SpectacularSwaggerView)

urlpatterns = [
    path("admin/", admin.site.urls),
    # API 문서
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
    # 앱 API
    path("api/elders/", include("apps.elders.urls")),
    path("api/risk/", include("apps.risk.urls")),
    path("api/weather/", include("apps.weather.urls")),
    path("api/alerts/", include("apps.alerts.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/ai/", include("apps.ai.urls")),
]
