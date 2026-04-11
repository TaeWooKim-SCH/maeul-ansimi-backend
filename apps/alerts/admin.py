from django.contrib import admin

from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = (
        "elder",
        "alert_type",
        "alert_level",
        "status",
        "sent_at",
        "responded_at",
    )
    list_filter = ("alert_type", "alert_level", "status")
    search_fields = ("elder__name", "note")
    list_per_page = 30
