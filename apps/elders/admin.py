from django.contrib import admin

from .models import CareWorker, Elder


@admin.register(Elder)
class ElderAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "age",
        "gender",
        "region_code",
        "health_grade",
        "is_deleted",
    )
    list_filter = (
        "gender",
        "health_grade",
        "housing_type",
        "lives_alone",
        "is_deleted",
    )
    search_fields = ("name", "address", "region_code")
    list_per_page = 30


@admin.register(CareWorker)
class CareWorkerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "region", "is_active")
    list_filter = ("is_active", "region")
    search_fields = ("name", "phone")
