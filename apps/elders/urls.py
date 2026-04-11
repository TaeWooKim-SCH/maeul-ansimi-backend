from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import ElderViewSet

app_name = "elders"

router = DefaultRouter()
router.register("", ElderViewSet, basename="elder")

urlpatterns: list = [
    path("", include(router.urls)),
]
