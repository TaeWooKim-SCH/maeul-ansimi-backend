"""개발 환경 설정"""

from .base import *  # noqa: F401,F403

DEBUG = True
ALLOWED_HOSTS = ["*"]

# 개발 시 BrowsableAPI 추가
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = [  # noqa: F405
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
]

# 개발 CORS 전체 허용
CORS_ALLOW_ALL_ORIGINS = True
