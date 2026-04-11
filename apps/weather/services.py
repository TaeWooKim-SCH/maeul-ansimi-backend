"""공공데이터 기상/대기질 API 연동 서비스"""

import logging
from datetime import datetime, timedelta
from typing import Any

import requests
from django.conf import settings
from django.core.cache import cache

from common.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)


# =============================================================================
# WeatherService — 기상청 API
# =============================================================================


class WeatherService:
    """기상청 공공데이터 API 연동"""

    BASE_URL = "https://apis.data.go.kr/1360000"

    def __init__(self) -> None:
        self.api_key: str = settings.DATA_GO_KR_API_KEY
        self.nx: int = settings.WEATHER_NX  # 65 (청양)
        self.ny: int = settings.WEATHER_NY  # 99 (청양)

    # ---- 초단기실황 ----

    def fetch_ultra_srt_ncst(self) -> dict[str, Any]:
        """기상청 초단기실황 API 호출 → 파싱된 관측 데이터 dict 반환"""
        base_date, base_time = self._get_base_time_ncst()
        url = f"{self.BASE_URL}/VilageFcstInfoService_2.0/getUltraSrtNcst"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": self.nx,
            "ny": self.ny,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        return self._parse_ncst_items(items, base_date, base_time)

    def _get_base_time_ncst(self) -> tuple[str, str]:
        """현재 시각 → 초단기실황 API base_date, base_time 변환.

        초단기실황은 매시 40분에 발표 → 현재 분이 40 미만이면 1시간 전 사용.
        """
        from django.utils import timezone as tz

        now = tz.localtime(tz.now())
        if now.minute < 40:
            now = now - timedelta(hours=1)
        base_date = now.strftime("%Y%m%d")
        base_time = now.strftime("%H00")
        return base_date, base_time

    def _parse_ncst_items(
        self, items: list[dict], base_date: str, base_time: str
    ) -> dict[str, Any]:
        """API 응답 items → 관측 데이터 dict 파싱.

        카테고리: T1H(기온), RN1(1시간 강수), UUU(동서 풍속), VVV(남북 풍속),
                REH(습도), PTY(강수형태), VEC(풍향), WSD(풍속)
        """
        parsed: dict[str, Any] = {
            "observed_at": datetime.strptime(f"{base_date}{base_time}", "%Y%m%d%H%M"),
        }
        category_map = {
            "T1H": "temperature",
            "RN1": "precipitation",
            "REH": "humidity",
            "WSD": "wind_speed",
        }
        for item in items:
            cat = item.get("category", "")
            val = item.get("obsrValue", "")
            if cat in category_map:
                try:
                    parsed[category_map[cat]] = float(val)
                except (ValueError, TypeError):
                    parsed[category_map[cat]] = None

        # 체감온도 계산
        temp = parsed.get("temperature")
        humidity = parsed.get("humidity")
        wind = parsed.get("wind_speed")
        if temp is not None:
            parsed["feels_like"] = self.calc_feels_like(temp, humidity, wind)

        return parsed

    # ---- 단기예보 ----

    def fetch_vilage_fcst(self) -> list[dict[str, Any]]:
        """기상청 단기예보 API 호출 → 예보 리스트 반환"""
        from django.utils import timezone as tz

        now = tz.localtime(tz.now())

        # 단기예보 발표시각: 0200, 0500, 0800, 1100, 1400, 1700, 2000, 2300
        announce_hours = [2, 5, 8, 11, 14, 17, 20, 23]
        base_hour = 23
        base_dt = now
        for h in sorted(announce_hours, reverse=True):
            candidate = now.replace(hour=h, minute=10, second=0, microsecond=0)
            if now >= candidate:
                base_hour = h
                break
        else:
            # 자정~02:10 사이 → 전날 23시
            base_dt = now - timedelta(days=1)
            base_hour = 23

        base_date = base_dt.strftime("%Y%m%d")
        base_time = f"{base_hour:02d}00"

        url = f"{self.BASE_URL}/VilageFcstInfoService_2.0/getVilageFcst"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 1000,
            "pageNo": 1,
            "dataType": "JSON",
            "base_date": base_date,
            "base_time": base_time,
            "nx": self.nx,
            "ny": self.ny,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        return self._parse_fcst_items(items)

    def _parse_fcst_items(self, items: list[dict]) -> list[dict[str, Any]]:
        """단기예보 items → 시각별 예보 dict 리스트 파싱"""
        # 시각별 그룹핑
        grouped: dict[str, dict[str, Any]] = {}
        for item in items:
            fcst_date = item.get("fcstDate", "")
            fcst_time = item.get("fcstTime", "")
            key = f"{fcst_date}{fcst_time}"
            if key not in grouped:
                grouped[key] = {
                    "forecast_at": datetime.strptime(key, "%Y%m%d%H%M"),
                }
            cat = item.get("category", "")
            val = item.get("fcstValue", "")
            if cat == "TMP":
                try:
                    grouped[key]["temperature"] = float(val)
                except (ValueError, TypeError):
                    pass
            elif cat == "REH":
                try:
                    grouped[key]["humidity"] = float(val)
                except (ValueError, TypeError):
                    pass
            elif cat == "POP":
                try:
                    grouped[key]["precipitation_prob"] = int(val)
                except (ValueError, TypeError):
                    pass
            elif cat == "SKY":
                sky_map = {"1": "맑음", "3": "구름많음", "4": "흐림"}
                grouped[key]["sky_condition"] = sky_map.get(val, val)

        return sorted(
            grouped.values(), key=lambda x: x.get("forecast_at", datetime.min)
        )

    # ---- 기상특보 ----

    def fetch_weather_alerts(self) -> list[dict[str, Any]]:
        """기상특보 API 호출 (stnId=133 대전지방기상청)"""
        from django.utils import timezone as tz

        now = tz.localtime(tz.now())
        url = f"{self.BASE_URL}/WthrWrnInfoService/getWthrWrnList"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "stnId": "133",
            "fromTmFc": (now - timedelta(days=1)).strftime("%Y%m%d"),
            "toTmFc": now.strftime("%Y%m%d"),
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        return self._parse_alert_items(items)

    def _parse_alert_items(self, items: list[dict]) -> list[dict[str, Any]]:
        """기상특보 items 파싱"""
        alerts: list[dict[str, Any]] = []
        alert_type_map = {
            "폭염": "폭염",
            "한파": "한파",
            "호우": "호우",
            "강풍": "강풍",
            "대설": "대설",
            "풍랑": "풍랑",
        }
        for item in items:
            title = item.get("title", "")
            # 청양 관련 특보만 필터링
            if "청양" not in title and "충남" not in title:
                continue

            alert_type = "기타"
            for keyword, atype in alert_type_map.items():
                if keyword in title:
                    alert_type = atype
                    break

            tmFc = item.get("tmFc", "")
            issued_at = None
            if tmFc:
                try:
                    issued_at = datetime.strptime(tmFc, "%Y%m%d%H%M")
                except ValueError:
                    try:
                        issued_at = datetime.strptime(tmFc, "%Y%m%d")
                    except ValueError:
                        pass

            alerts.append(
                {
                    "alert_type": alert_type,
                    "region": "충남 청양군",
                    "issued_at": issued_at,
                    "title": title,
                }
            )
        return alerts

    # ---- 체감온도 ----

    # ---- 생활기상지수 ----

    # 생활기상지수 V4 공통
    _LIVING_IDX_URL = (
        "https://apis.data.go.kr/1360000/LivingWthrIdxServiceV4/getSenTaIdxV4"
    )

    def _fetch_living_index(self, request_code: str) -> dict[str, Any]:
        """생활기상지수 V4 공통 호출 (requestCode로 지수 종류 구분)."""
        from django.utils import timezone as tz

        now = tz.localtime(tz.now())
        # 00시 기준으로 요청 (발표 주기에 맞춤)
        time_param = now.strftime("%Y%m%d") + "00"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "areaNo": "4477000000",  # 충남 청양군
            "time": time_param,
            "requestCode": request_code,
        }
        resp = requests.get(self._LIVING_IDX_URL, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        result_code = data.get("response", {}).get("header", {}).get("resultCode", "")
        if result_code == "03":
            # NO_DATA — 비계절 (여름에 체감온도, 겨울에 열지수 등)
            return {}

        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not items:
            return {}

        item = items[0]
        return {
            "code": request_code,
            "h3": self._safe_int(item.get("h3")),
            "h6": self._safe_int(item.get("h6")),
            "h9": self._safe_int(item.get("h9")),
            "h24": self._safe_int(item.get("h24")),
            "h48": self._safe_int(item.get("h48")),
            "h72": self._safe_int(item.get("h72")),
        }

    def fetch_heat_index(self) -> dict[str, Any]:
        """더위체감지수 (A05) — 여름 한정, 비시즌에는 빈 dict 반환"""
        return self._fetch_living_index("A05")

    def fetch_wind_chill_index(self) -> dict[str, Any]:
        """체감온도지수 (A06) — 겨울 한정, 비시즌에는 빈 dict 반환"""
        return self._fetch_living_index("A06")

    def fetch_uv_index(self) -> dict[str, Any]:
        """자외선지수 (A07_2) — 연중 제공"""
        return self._fetch_living_index("A07_2")

    def fetch_air_diffusion_index(self) -> dict[str, Any]:
        """대기확산지수 (A09) — 연중 제공"""
        return self._fetch_living_index("A09")

    # ---- 중기예보 ----

    def _get_mid_base_time(self) -> str:
        """중기예보 발표시각 (06시, 18시) → tmFc 문자열"""
        from django.utils import timezone as tz

        now = tz.localtime(tz.now())
        if now.hour < 6:
            base = (now - timedelta(days=1)).replace(hour=18, minute=0, second=0)
        elif now.hour < 18:
            base = now.replace(hour=6, minute=0, second=0)
        else:
            base = now.replace(hour=18, minute=0, second=0)
        return base.strftime("%Y%m%d%H%M")

    def fetch_mid_temperature(self) -> dict[str, Any]:
        """중기기온 조회 (보령 — 청양 인접 지점)"""
        tm_fc = self._get_mid_base_time()
        url = f"{self.BASE_URL}/MidFcstInfoService/getMidTa"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "regId": "11C20301",  # 보령 (청양 인접, 광역 코드는 0 반환)
            "tmFc": tm_fc,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not items:
            return {}

        item = items[0]
        result: dict[str, Any] = {"type": "mid_temperature"}
        # 중기기온은 day3(~4)부터 제공, 지점에 따라 day4/5부터 유효
        for day in range(3, 11):
            val_min = self._safe_float_val(item.get(f"taMin{day}"))
            val_max = self._safe_float_val(item.get(f"taMax{day}"))
            if val_min is not None and val_min != 0:
                result[f"day{day}_min"] = val_min
            if val_max is not None and val_max != 0:
                result[f"day{day}_max"] = val_max
        return result

    def fetch_mid_land_forecast(self) -> dict[str, Any]:
        """중기육상예보 (충남)"""
        tm_fc = self._get_mid_base_time()
        url = f"{self.BASE_URL}/MidFcstInfoService/getMidLandFcst"
        params = {
            "serviceKey": self.api_key,
            "numOfRows": 10,
            "pageNo": 1,
            "dataType": "JSON",
            "regId": "11C20000",  # 충남 (육상예보는 광역 코드 사용)
            "tmFc": tm_fc,
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = (
            data.get("response", {}).get("body", {}).get("items", {}).get("item", [])
        )
        if not items:
            return {}

        item = items[0]
        result: dict[str, Any] = {"type": "mid_land_forecast"}
        for day in range(3, 11):
            result[f"day{day}_rain_am"] = self._safe_int(item.get(f"rnSt{day}Am"))
            result[f"day{day}_rain_pm"] = self._safe_int(item.get(f"rnSt{day}Pm"))
            result[f"day{day}_sky_am"] = item.get(f"wf{day}Am", "")
            result[f"day{day}_sky_pm"] = item.get(f"wf{day}Pm", "")
        return result

    @staticmethod
    def _safe_int(val: Any) -> int | None:
        if val is None or val == "":
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _safe_float_val(val: Any) -> float | None:
        if val is None or val == "":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def calc_feels_like(
        temp: float,
        humidity: float | None = None,
        wind_speed: float | None = None,
    ) -> float:
        """체감온도 계산.

        - temp >= 27℃ → Heat Index (습도 필요)
        - temp <= 10℃ && wind >= 1.3 → Wind Chill
        - 그 외 → 기온 그대로
        """
        if temp >= 27 and humidity is not None:
            # Heat Index (Rothfusz)
            hi = (
                -8.784
                + 1.611 * temp
                + 2.338 * humidity
                - 0.146 * temp * humidity
                - 0.01230 * temp**2
                - 0.01642 * humidity**2
                + 0.002211 * temp**2 * humidity
                + 0.000725 * temp * humidity**2
                - 0.000003582 * temp**2 * humidity**2
            )
            return round(hi, 1)

        if temp <= 10 and wind_speed is not None and wind_speed >= 1.3:
            # Wind Chill
            wc = (
                13.12
                + 0.6215 * temp
                - 11.37 * wind_speed**0.16
                + 0.3965 * temp * wind_speed**0.16
            )
            return round(wc, 1)

        return round(temp, 1)


# =============================================================================
# AirQualityService — 에어코리아 API
# =============================================================================


class AirQualityService:
    """에어코리아 실시간 대기오염 API 연동"""

    BASE_URL = "https://apis.data.go.kr/B552584/ArpltnInforInqireSvc"

    def __init__(self) -> None:
        self.api_key: str = settings.DATA_GO_KR_API_KEY
        self.station_name: str = settings.AIR_QUALITY_STATION  # "청양"

    def fetch_realtime(self) -> dict[str, Any]:
        """에어코리아 측정소별 실시간 대기오염 조회"""
        url = f"{self.BASE_URL}/getMsrstnAcctoRltmMesureDnsty"
        params = {
            "serviceKey": self.api_key,
            "returnType": "json",
            "numOfRows": 1,
            "pageNo": 1,
            "stationName": self.station_name,
            "dataTerm": "DAILY",
            "ver": "1.0",
        }
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()

        data = resp.json()
        items = data.get("response", {}).get("body", {}).get("items", [])
        if not items:
            return {}

        item = items[0]
        pm25 = self._safe_float(item.get("pm25Value"))
        pm10 = self._safe_float(item.get("pm10Value"))
        ozone = self._safe_float(item.get("o3Value"))

        return {
            "pm25": pm25,
            "pm25_grade": self._get_grade(pm25, "pm25"),
            "pm10": pm10,
            "ozone": ozone,
            "data_time": item.get("dataTime", ""),
        }

    @staticmethod
    def _safe_float(val: Any) -> float | None:
        if val is None or val == "" or val == "-":
            return None
        try:
            return float(val)
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _get_grade(value: float | None, pollutant: str) -> str:
        """PM/오존 수치 → 등급(좋음/보통/나쁨/매우나쁨)"""
        if value is None:
            return ""
        thresholds = {
            "pm25": [
                (15, "좋음"),
                (35, "보통"),
                (75, "나쁨"),
                (float("inf"), "매우나쁨"),
            ],
            "pm10": [
                (30, "좋음"),
                (80, "보통"),
                (150, "나쁨"),
                (float("inf"), "매우나쁨"),
            ],
            "ozone": [
                (0.03, "좋음"),
                (0.09, "보통"),
                (0.15, "나쁨"),
                (float("inf"), "매우나쁨"),
            ],
        }
        for limit, label in thresholds.get(pollutant, []):
            if value <= limit:
                return label
        return ""


# =============================================================================
# Fallback 래퍼
# =============================================================================


class WeatherServiceWithFallback:
    """공공데이터 API 호출 시 try/except + cache fallback + ServiceUnavailableError"""

    CACHE_KEY = "weather:current"
    CACHE_TTL = 3600  # 1시간

    def __init__(self) -> None:
        self.weather_service = WeatherService()
        self.air_quality_service = AirQualityService()

    def get_weather_observation(self) -> dict[str, Any]:
        try:
            data = self.weather_service.fetch_ultra_srt_ncst()
            cache.set(self.CACHE_KEY, data, self.CACHE_TTL)
            return data
        except Exception as e:
            logger.warning("기상 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(self.CACHE_KEY)
            if cached:
                return cached
            raise ServiceUnavailableError("기상 데이터를 가져올 수 없습니다.") from e

    def get_weather_forecast(self) -> list[dict[str, Any]]:
        cache_key = "weather:forecast"
        try:
            data = self.weather_service.fetch_vilage_fcst()
            cache.set(cache_key, data, self.CACHE_TTL)
            return data
        except Exception as e:
            logger.warning("예보 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(cache_key)
            if cached:
                return cached
            raise ServiceUnavailableError("예보 데이터를 가져올 수 없습니다.") from e

    def get_weather_alerts(self) -> list[dict[str, Any]]:
        cache_key = "weather:alerts"
        try:
            data = self.weather_service.fetch_weather_alerts()
            cache.set(cache_key, data, 600)
            return data
        except Exception as e:
            logger.warning("기상특보 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(cache_key)
            if cached:
                return cached
            raise ServiceUnavailableError(
                "기상특보 데이터를 가져올 수 없습니다."
            ) from e

    def get_air_quality(self) -> dict[str, Any]:
        cache_key = "weather:air_quality"
        try:
            data = self.air_quality_service.fetch_realtime()
            cache.set(cache_key, data, self.CACHE_TTL)
            return data
        except Exception as e:
            logger.warning("대기질 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(cache_key)
            if cached:
                return cached
            raise ServiceUnavailableError("대기질 데이터를 가져올 수 없습니다.") from e

    def get_living_weather_index(self) -> dict[str, Any]:
        """생활기상지수 (더위체감 / 체감온도) 조회 + 캐시"""
        cache_key = "weather:living_index"
        try:
            heat = self.weather_service.fetch_heat_index()
            wind_chill = self.weather_service.fetch_wind_chill_index()
            data = {"heat_index": heat, "wind_chill_index": wind_chill}
            cache.set(cache_key, data, self.CACHE_TTL)
            return data
        except Exception as e:
            logger.warning("생활기상지수 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(cache_key)
            if cached:
                return cached
            return {}

    def get_mid_forecast(self) -> dict[str, Any]:
        """중기예보 (기온 + 육상예보) 조회 + 캐시"""
        cache_key = "weather:mid_forecast"
        try:
            mid_temp = self.weather_service.fetch_mid_temperature()
            mid_land = self.weather_service.fetch_mid_land_forecast()
            data = {"mid_temperature": mid_temp, "mid_land_forecast": mid_land}
            cache.set(cache_key, data, self.CACHE_TTL)
            return data
        except Exception as e:
            logger.warning("중기예보 API 호출 실패, 캐시 fallback 시도: %s", e)
            cached = cache.get(cache_key)
            if cached:
                return cached
            return {}


# =============================================================================
# AI 엔진 입력 변환
# =============================================================================


def build_weather_condition(observation) -> dict[str, Any]:
    """DB WeatherObservation → AI 엔진 입력 dict 변환"""
    if observation is None:
        return {}
    return {
        "temperature": float(observation.temperature),
        "feels_like": float(observation.feels_like) if observation.feels_like else None,
        "humidity": float(observation.humidity) if observation.humidity else None,
        "wind_speed": float(observation.wind_speed) if observation.wind_speed else None,
        "precipitation": float(observation.precipitation),
        "pm25": float(observation.pm25) if observation.pm25 else None,
        "pm25_grade": observation.pm25_grade,
        "pm10": float(observation.pm10) if observation.pm10 else None,
        "ozone": float(observation.ozone) if observation.ozone else None,
        "weather_alert": observation.weather_alert or None,
    }
