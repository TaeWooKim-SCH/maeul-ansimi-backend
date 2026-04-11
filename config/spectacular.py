"""drf-spectacular 전처리 훅 — URL prefix 기반 태그 자동 매핑"""

TAG_MAP: dict[str, str] = {
    "/api/elders/": "대상자",
    "/api/risk/": "위험도",
    "/api/weather/": "기상",
    "/api/alerts/": "알림",
    "/api/dashboard/": "대시보드",
    "/api/ai/": "AI",
}


def preprocess_tag_by_url(endpoints: list, **kwargs) -> list:  # noqa: ARG001
    """엔드포인트 URL prefix → 한글 태그 자동 부여"""
    for path, path_regex, method, callback in endpoints:
        for prefix, tag in TAG_MAP.items():
            if path.startswith(prefix):
                callback.cls.kwargs = getattr(callback.cls, "kwargs", {})
                if not hasattr(callback, "initkwargs"):
                    callback.initkwargs = {}
                callback.initkwargs.setdefault("tags", [tag])
                break
    return endpoints
