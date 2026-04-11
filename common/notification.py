"""카카오 알림톡 발송 서비스 (시뮬레이션 모드 포함)"""

import logging
from typing import Any

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# 알림 템플릿 정의
TEMPLATES: dict[str, str] = {
    "안부확인": (
        "[마을안심이] {elder_name}님 안부확인\n"
        "현재 위험등급: {risk_level}\n"
        "주요 위험요인: {top_factor}\n"
        "안전 여부를 확인해 주세요."
    ),
    "긴급방문": (
        "[마을안심이] 긴급 방문 요청\n"
        "{elder_name}님 ({age}세, {region})\n"
        "위험등급: {risk_level} (점수: {score}점)\n"
        "즉시 방문 확인이 필요합니다."
    ),
    "보호자알림": (
        "[마을안심이] 보호자 알림\n"
        "{elder_name}님의 위험등급이 '{risk_level}'으로 상승했습니다.\n"
        "주요 원인: {top_factor}\n"
        "담당자가 확인 중이며, 필요시 연락드리겠습니다."
    ),
}


class KakaoNotificationService:
    """카카오 알림톡 발송 서비스.

    KAKAO_REST_API_KEY가 설정되어 있으면 실제 발송을 시도하고,
    비어 있으면 시뮬레이션 모드로 로그만 남긴다.
    """

    def __init__(self) -> None:
        self.api_key: str = getattr(settings, "KAKAO_REST_API_KEY", "")
        self.simulation_mode: bool = not bool(self.api_key)

    def send(
        self,
        phone: str,
        template_key: str,
        variables: dict[str, Any],
    ) -> dict[str, Any]:
        """알림톡 발송 (실제 or 시뮬레이션).

        Returns:
            {"success": bool, "mode": "live"|"simulation", "message": str}
        """
        template = TEMPLATES.get(template_key)
        if template is None:
            logger.warning("알림 템플릿 '%s' 없음", template_key)
            return {"success": False, "mode": "error", "message": "템플릿 없음"}

        message = template.format(**variables)

        if self.simulation_mode:
            return self._send_simulation(phone, template_key, message)

        return self._send_live(phone, message)

    def _send_simulation(
        self, phone: str, template_key: str, message: str
    ) -> dict[str, Any]:
        """시뮬레이션 모드: 로그만 남김"""
        logger.info(
            "[알림톡 시뮬레이션] to=%s template=%s\n%s",
            phone,
            template_key,
            message,
        )
        return {
            "success": True,
            "mode": "simulation",
            "message": message,
        }

    def _send_live(self, phone: str, message: str) -> dict[str, Any]:
        """실제 카카오 알림톡 API 호출"""
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {
            "template_object": {
                "object_type": "text",
                "text": message,
                "link": {"web_url": "", "mobile_web_url": ""},
            }
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            resp.raise_for_status()
            logger.info("[알림톡 발송] to=%s 성공", phone)
            return {"success": True, "mode": "live", "message": message}
        except Exception as e:
            logger.error("[알림톡 발송 실패] to=%s error=%s", phone, e)
            return {"success": False, "mode": "live", "message": str(e)}
