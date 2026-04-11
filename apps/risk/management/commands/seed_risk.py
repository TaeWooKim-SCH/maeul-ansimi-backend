"""시드 대상자 기반 초기 위험도 계산"""

from django.core.management.base import BaseCommand

from apps.ai.engine import RiskScoringEngine
from apps.elders.models import Elder
from apps.risk.models import RiskScore
from apps.weather.models import WeatherObservation
from apps.weather.services import build_weather_condition


class Command(BaseCommand):
    help = "시드 대상자 기반 초기 위험도 일괄 계산"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="기존 위험도 데이터 삭제 후 계산",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = RiskScore.objects.all().delete()
            self.stdout.write(f"기존 위험도 데이터 {deleted}건 삭제")

        weather_obs = WeatherObservation.objects.order_by("-observed_at").first()
        if weather_obs is None:
            self.stdout.write(
                self.style.WARNING(
                    "기상 데이터가 없습니다. seed_weather를 먼저 실행하세요."
                )
            )
            return

        weather_condition = build_weather_condition(weather_obs)
        engine = RiskScoringEngine()

        elders = Elder.objects.filter(is_deleted=False)
        total = elders.count()

        if total == 0:
            self.stdout.write(
                self.style.WARNING("대상자가 없습니다. seed_elders를 먼저 실행하세요.")
            )
            return

        risk_scores: list[RiskScore] = []
        for elder in elders.iterator(chunk_size=100):
            profile = elder.to_risk_profile()
            result = engine.calculate(profile, weather_condition)
            risk_scores.append(
                RiskScore(
                    elder=elder,
                    weather_risk=result["weather_risk"],
                    health_risk=result["health_risk"],
                    housing_risk=result["housing_risk"],
                    isolation_risk=result["isolation_risk"],
                    total_score=result["total_score"],
                    risk_level=result["risk_level"],
                    feature_importance=result.get("feature_importance", {}),
                    model_version=result["model_version"],
                )
            )

        RiskScore.objects.bulk_create(risk_scores)

        # 등급별 통계 출력
        level_counts: dict[str, int] = {}
        for rs in risk_scores:
            level_counts[rs.risk_level] = level_counts.get(rs.risk_level, 0) + 1

        self.stdout.write(self.style.SUCCESS(f"위험도 계산 완료: {len(risk_scores)}명"))
        for level in ["관심", "주의", "경계", "심각"]:
            cnt = level_counts.get(level, 0)
            pct = round(cnt / len(risk_scores) * 100, 1) if risk_scores else 0
            self.stdout.write(f"  {level}: {cnt}명 ({pct}%)")
