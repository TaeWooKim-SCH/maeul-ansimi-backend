"""청양군 8개 읍면 300명 테스트 대상자 시드 데이터 생성"""

import random
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.elders.models import CareWorker, Elder
from apps.elders.serializers import CHEONGYANG_REGIONS, VISIT_FREQ_SCORES

# 질환 풀
DISEASES_POOL: list[str] = [
    "고혈압",
    "당뇨",
    "심부전",
    "뇌졸중",
    "관절염",
    "호흡기질환",
    "천식",
    "치매",
    "골다공증",
    "백내장",
]

# 성별별 이름 풀
LAST_NAMES: list[str] = ["김", "이", "박", "최", "정", "조", "강", "윤", "장", "한"]
MALE_FIRST_NAMES: list[str] = [
    "영수",
    "정호",
    "성근",
    "순호",
    "태호",
    "광호",
    "진수",
    "병철",
    "동식",
    "용호",
    "기남",
    "상호",
    "만수",
    "득수",
    "재호",
]
FEMALE_FIRST_NAMES: list[str] = [
    "순이",
    "영자",
    "정숙",
    "춘자",
    "옥순",
    "복순",
    "금순",
    "말순",
    "점순",
    "분이",
    "귀남",
    "선이",
    "미자",
    "경자",
    "순자",
]

HOUSING_TYPES: list[str] = ["단독주택", "아파트", "다세대", "연립", "기타"]
HOUSING_TYPE_WEIGHTS: list[float] = [0.60, 0.10, 0.10, 0.10, 0.10]

VISIT_FREQS: list[str] = ["매일", "주3회", "주2회", "주1회", "격주", "월1회", "없음"]
VISIT_FREQ_WEIGHTS: list[float] = [0.03, 0.07, 0.15, 0.35, 0.15, 0.15, 0.10]

HEALTH_GRADES: list[str] = ["양호", "주의", "위험"]
HEALTH_GRADE_WEIGHTS: list[float] = [0.45, 0.35, 0.20]


def _random_name(gender: str) -> str:
    last = random.choice(LAST_NAMES)
    first = random.choice(MALE_FIRST_NAMES if gender == "M" else FEMALE_FIRST_NAMES)
    return f"{last}{first}"


def _random_diseases() -> list[str]:
    count = random.choices(
        [0, 1, 2, 3, 4, 5], weights=[0.10, 0.25, 0.30, 0.20, 0.10, 0.05]
    )[0]
    return random.sample(DISEASES_POOL, min(count, len(DISEASES_POOL)))


def _jitter(base: float, spread: float = 0.01) -> Decimal:
    return Decimal(str(round(base + random.uniform(-spread, spread), 7)))


class Command(BaseCommand):
    help = "청양군 8개 읍면 300명 테스트 대상자 생성"

    def add_arguments(self, parser):
        parser.add_argument(
            "--count",
            type=int,
            default=300,
            help="생성할 대상자 수 (기본값 300)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="기존 대상자 데이터 삭제 후 생성",
        )

    def handle(self, *args, **options):
        count: int = options["count"]
        clear: bool = options["clear"]

        if clear:
            deleted_elders, _ = Elder.objects.all().delete()
            deleted_workers, _ = CareWorker.objects.all().delete()
            self.stdout.write(
                f"기존 데이터 삭제: 대상자 {deleted_elders}명, 돌봄관리사 {deleted_workers}명"
            )

        # 돌봄관리사 시드
        care_workers: list[CareWorker] = []
        for region in CHEONGYANG_REGIONS:
            cw, _ = CareWorker.objects.get_or_create(
                name=f"{region['name']} 담당자",
                defaults={
                    "phone": f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                    "region": region["name"],
                    "is_active": True,
                },
            )
            care_workers.append(cw)

        self.stdout.write(f"돌봄관리사 {len(care_workers)}명 준비 완료")

        # 대상자 시드
        elders_to_create: list[Elder] = []
        per_region = count // len(CHEONGYANG_REGIONS)
        remainder = count % len(CHEONGYANG_REGIONS)

        for idx, region in enumerate(CHEONGYANG_REGIONS):
            region_count = per_region + (1 if idx < remainder else 0)
            cw = care_workers[idx]

            for _ in range(region_count):
                gender = random.choice(["M", "F"])
                name = _random_name(gender)
                age = random.randint(65, 98)
                diseases = _random_diseases()
                lives_alone = random.random() < 0.75
                has_guardian = random.random() < 0.55

                visit_freq = random.choices(VISIT_FREQS, weights=VISIT_FREQ_WEIGHTS)[0]
                isolation_score = Decimal("0")
                if lives_alone:
                    isolation_score += Decimal("30")
                if not has_guardian:
                    isolation_score += Decimal("20")
                isolation_score += VISIT_FREQ_SCORES.get(visit_freq, Decimal("50"))
                isolation_score = min(isolation_score, Decimal("100"))

                housing_type = random.choices(
                    HOUSING_TYPES, weights=HOUSING_TYPE_WEIGHTS
                )[0]

                elders_to_create.append(
                    Elder(
                        name=name,
                        age=age,
                        gender=gender,
                        address=f"충남 청양군 {region['name']} 테스트리 {random.randint(1, 500)}번지",
                        lat=_jitter(region["lat"]),
                        lng=_jitter(region["lng"]),
                        region_code=region["code"],
                        diseases=diseases,
                        disease_count=len(diseases),
                        bmi=Decimal(str(round(random.uniform(16.0, 32.0), 1))),
                        health_grade=random.choices(
                            HEALTH_GRADES, weights=HEALTH_GRADE_WEIGHTS
                        )[0],
                        medications=[f"약품{i}" for i in range(len(diseases))],
                        recent_hospital=random.random() < 0.15,
                        housing_type=housing_type,
                        building_year=random.randint(1975, 2020),
                        has_cooling=random.random() < 0.40,
                        has_heating=random.random() < 0.85,
                        flood_risk=random.random() < 0.12,
                        lives_alone=lives_alone,
                        has_guardian=has_guardian,
                        guardian_phone=(
                            f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}"
                            if has_guardian
                            else ""
                        ),
                        care_visit_freq=visit_freq,
                        care_worker=cw,
                        isolation_score=isolation_score,
                    )
                )

        Elder.objects.bulk_create(elders_to_create)
        self.stdout.write(
            self.style.SUCCESS(f"대상자 {len(elders_to_create)}명 생성 완료!")
        )

        # 지역별 통계
        for region in CHEONGYANG_REGIONS:
            cnt = Elder.objects.filter(
                region_code=region["code"], is_deleted=False
            ).count()
            self.stdout.write(f"  {region['name']} ({region['code']}): {cnt}명")
