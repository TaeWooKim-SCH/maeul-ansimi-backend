"""마을안심이 AI 위험도 산출 엔진.

RiskScoringEngine: 규칙 기반 위험도 산출 (rule-v1.0)
- Elder 프로필 + 기상 조건 → 4개 하위점수 + 종합점수 + 등급 + 기여도
- 교차위험 보정계수 적용 (기상×질환)
- 향후 ML 모델 교체 시 이 클래스만 대체하면 됨
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# 기상×질환 교차위험 보정계수
CROSS_RISK_TABLE: dict[tuple[str, str], float] = {
    ("폭염", "심부전"): 1.3,
    ("폭염", "고혈압"): 1.2,
    ("폭염", "당뇨"): 1.15,
    ("폭염", "뇌졸중"): 1.25,
    ("폭염", "호흡기질환"): 1.2,
    ("한파", "심부전"): 1.3,
    ("한파", "고혈압"): 1.25,
    ("한파", "뇌졸중"): 1.3,
    ("한파", "관절염"): 1.15,
    ("미세먼지", "호흡기질환"): 1.3,
    ("미세먼지", "천식"): 1.35,
}

# 등급 임계값
LEVEL_THRESHOLDS: list[tuple[float, str]] = [
    (71, "심각"),
    (51, "경계"),
    (31, "주의"),
    (0, "관심"),
]

# 가중치
WEIGHTS: dict[str, float] = {
    "weather": 0.35,
    "health": 0.30,
    "housing": 0.20,
    "isolation": 0.15,
}

MODEL_VERSION = "rule-v1.0"


class RiskScoringEngine:
    """규칙 기반 위험도 산출 엔진.

    사용법::

        engine = RiskScoringEngine()
        result = engine.calculate(profile, weather_condition)
        # result = {
        #     "weather_risk", "health_risk", "housing_risk", "isolation_risk",
        #     "total_score", "risk_level", "feature_importance", "model_version"
        # }
    """

    version: str = MODEL_VERSION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(
        self,
        profile: dict[str, Any],
        weather: dict[str, Any],
    ) -> dict[str, Any]:
        """Elder 프로필 + 기상 조건 → 위험도 결과 dict 반환.

        Args:
            profile: Elder.to_risk_profile() 반환값 (17개 필드)
            weather: build_weather_condition() 반환값 (기상 10개 필드)

        Returns:
            weather_risk, health_risk, housing_risk, isolation_risk,
            total_score, risk_level, feature_importance, model_version
        """
        importance: dict[str, float] = {}

        weather_risk = self._calc_weather_risk(weather, importance)
        health_risk = self._calc_health_risk(profile, importance)
        housing_risk = self._calc_housing_risk(profile, weather, importance)
        isolation_risk = self._calc_isolation_risk(profile, importance)

        cross_multiplier = self._calc_cross_multiplier(profile, weather)

        total = (
            weather_risk * WEIGHTS["weather"]
            + health_risk * WEIGHTS["health"]
            + housing_risk * WEIGHTS["housing"]
            + isolation_risk * WEIGHTS["isolation"]
        ) * cross_multiplier
        total = min(round(total, 2), 100)

        risk_level = self._determine_level(total)

        return {
            "weather_risk": round(weather_risk, 2),
            "health_risk": round(health_risk, 2),
            "housing_risk": round(housing_risk, 2),
            "isolation_risk": round(isolation_risk, 2),
            "total_score": total,
            "risk_level": risk_level,
            "feature_importance": importance,
            "model_version": self.version,
        }

    # ------------------------------------------------------------------
    # 하위 점수 산출
    # ------------------------------------------------------------------

    def _calc_weather_risk(
        self, weather: dict[str, Any], importance: dict[str, float]
    ) -> float:
        """기상 위험도 (0~100)"""
        score = 0.0
        temp = weather.get("temperature")

        if temp is not None:
            feels_like = weather.get("feels_like", temp)
            if feels_like is not None:
                if feels_like >= 35:
                    score += 40
                    importance["temperature"] = 40
                elif feels_like >= 33:
                    score += 30
                    importance["temperature"] = 30
                elif feels_like >= 28:
                    score += 15
                    importance["temperature"] = 15
                elif feels_like <= -15:
                    score += 40
                    importance["temperature"] = 40
                elif feels_like <= -10:
                    score += 30
                    importance["temperature"] = 30
                elif feels_like <= 0:
                    score += 15
                    importance["temperature"] = 15

        pm25 = weather.get("pm25")
        if pm25 is not None:
            if pm25 > 150:
                score += 30
                importance["pm25"] = 30
            elif pm25 > 75:
                score += 20
                importance["pm25"] = 20
            elif pm25 > 35:
                score += 10
                importance["pm25"] = 10

        if weather.get("weather_alert"):
            score += 20
            importance["weather_alert"] = 20

        precipitation = weather.get("precipitation", 0)
        if precipitation and precipitation > 30:
            score += 10
            importance["precipitation"] = 10

        return min(score, 100)

    def _calc_health_risk(
        self, profile: dict[str, Any], importance: dict[str, float]
    ) -> float:
        """건강 위험도 (0~100)"""
        score = 0.0

        disease_count = profile.get("disease_count", 0)
        if disease_count >= 4:
            score += 35
            importance["disease_count"] = 35
        elif disease_count >= 2:
            score += 20
            importance["disease_count"] = 20
        elif disease_count >= 1:
            score += 10
            importance["disease_count"] = 10

        health_grade = profile.get("health_grade", "양호")
        if health_grade == "위험":
            score += 30
            importance["health_grade"] = 30
        elif health_grade == "주의":
            score += 15
            importance["health_grade"] = 15

        if profile.get("recent_hospital"):
            score += 20
            importance["recent_hospital"] = 20

        bmi = profile.get("bmi")
        if bmi is not None:
            if bmi < 18.5 or bmi > 30:
                score += 15
                importance["bmi"] = 15
            elif bmi > 25:
                score += 5
                importance["bmi"] = 5

        return min(score, 100)

    def _calc_housing_risk(
        self,
        profile: dict[str, Any],
        weather: dict[str, Any],
        importance: dict[str, float],
    ) -> float:
        """주거 위험도 (0~100)"""
        score = 0.0
        temp = weather.get("temperature")

        if profile.get("housing_type") == "단독주택":
            score += 15
            importance["housing_type"] = 15

        building_year = profile.get("building_year")
        if building_year is not None and building_year < 1990:
            score += 20
            importance["building_year"] = 20
        elif building_year is not None and building_year < 2000:
            score += 10
            importance["building_year"] = 10

        if not profile.get("has_cooling") and temp is not None and temp >= 28:
            score += 25
            importance["has_cooling"] = 25

        if not profile.get("has_heating") and temp is not None and temp <= 5:
            score += 25
            importance["has_heating"] = 25

        if profile.get("flood_risk"):
            score += 15
            importance["flood_risk"] = 15

        return min(score, 100)

    def _calc_isolation_risk(
        self, profile: dict[str, Any], importance: dict[str, float]
    ) -> float:
        """고립 위험도 (0~100)"""
        score = float(profile.get("isolation_score", 0))

        if profile.get("lives_alone"):
            importance["lives_alone"] = 30
        if not profile.get("has_guardian"):
            importance["has_guardian"] = 20

        last_contact = profile.get("last_contact")
        if last_contact is None:
            score += 15
            importance["last_contact"] = 15

        return min(score, 100)

    # ------------------------------------------------------------------
    # 교차위험 & 등급
    # ------------------------------------------------------------------

    def _calc_cross_multiplier(
        self, profile: dict[str, Any], weather: dict[str, Any]
    ) -> float:
        """기상×질환 교차위험 보정계수 (최대값 1개 적용)"""
        temp = weather.get("temperature")
        pm25 = weather.get("pm25")
        alert_text = weather.get("weather_alert", "") or ""
        diseases: list[str] = profile.get("diseases", [])

        weather_type = ""
        if "폭염" in alert_text or (temp is not None and temp >= 33):
            weather_type = "폭염"
        elif "한파" in alert_text or (temp is not None and temp <= -10):
            weather_type = "한파"
        elif pm25 is not None and pm25 > 75:
            weather_type = "미세먼지"

        if not weather_type or not diseases:
            return 1.0

        multiplier = 1.0
        for disease in diseases:
            m = CROSS_RISK_TABLE.get((weather_type, disease), 1.0)
            if m > multiplier:
                multiplier = m
        return multiplier

    @staticmethod
    def _determine_level(total_score: float) -> str:
        """종합 점수 → 위험 등급"""
        for threshold, level in LEVEL_THRESHOLDS:
            if total_score >= threshold:
                return level
        return "관심"
