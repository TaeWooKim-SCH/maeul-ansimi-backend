"""테스트 환경 설정 — Docker PostgreSQL + Redis 사용"""

from .base import *  # noqa: F401,F403

# DB: base.py의 DATABASE_URL(PostgreSQL) 그대로 사용
# Cache: base.py의 REDIS_URL(django-redis) 그대로 사용

# Celery 동기 실행 (워커 없이 테스트 가능)
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
