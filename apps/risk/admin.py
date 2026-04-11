from django.contrib import admin

from .models import RiskScore


@admin.register(RiskScore)
class RiskScoreAdmin(admin.ModelAdmin):
    list_display = ("elder", "risk_level", "total_score", "scored_at", "model_version")
    list_filter = ("risk_level", "model_version")
    search_fields = ("elder__name",)
    list_per_page = 30
