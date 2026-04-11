# 마을안심이 백엔드

충남 청양군 고령 독거노인을 위한 AI 기반 안전관리 플랫폼의 백엔드 API 서버입니다.

기상 데이터와 개인 건강/주거/사회적 요인을 종합 분석하여 위험도를 산출하고, 등급 변화에 따라 자동으로 안부전화, 방문배정, 긴급출동 등의 알림을 생성합니다.

## 기술 스택

| 구분 | 기술 |
|------|------|
| Framework | Django 5.2, Django REST Framework 3.17 |
| Database | PostgreSQL + psycopg2 |
| Cache / Broker | Redis (django-redis) |
| Task Queue | Celery 5.6 + django-celery-beat |
| API 문서 | drf-spectacular (OpenAPI 3.0) |
| 외부 연동 | 기상청 API, 에어코리아 API, 카카오 알림톡 |
| 코드 품질 | Black, isort, flake8, coverage |
| 배포 | Docker, docker-compose, Gunicorn |

## 주요 기능

### 대상자 관리
- 고령 독거노인 등록/조회/수정/소프트 삭제
- 질환, 주거환경, 사회적 고립도 등 다차원 프로필 관리
- 읍면 코드 자동 매핑 및 초기 고립도 점수 산출

### AI 위험도 분석
- **4개 하위 지표** 종합 산출 (가중치 합산 + 교차위험 보정)
  - 기상 위험도 (35%) — 체감온도, 강수, 미세먼지, 기상특보
  - 건강 위험도 (30%) — 질환 종류/수, BMI, 건강등급
  - 주거 위험도 (20%) — 주택유형, 건축년도, 냉난방, 침수위험
  - 고립 위험도 (15%) — 독거, 보호자, 방문주기, 최근연락
- **위험 등급**: 관심(0-30) / 주의(31-50) / 경계(51-70) / 심각(71-100)
- 11개 기상x질환 교차위험 쌍 보정 (예: 폭염x심부전 = 1.3배)

### 자동 알림 체계
- 등급 상승 감지 시 자동 알림 생성
  - 주의 → 안부전화 (AI 음성 안부확인)
  - 경계 → 방문배정 (돌봄관리사 긴급방문 + 보호자 알림)
  - 심각 → 긴급출동 (119 준비 + 보호자 긴급연락)
- 카카오 알림톡 연동 (시뮬레이션 모드 지원)

### 공공데이터 자동 수집
- 기상청 초단기실황 (30분), 단기예보 (3시간), 기상특보 (10분)
- 에어코리아 실시간 대기오염 (1시간)
- 생활기상지수 (3시간), 중기예보 (6시간)

### 대시보드
- 종합 현황 (대상자 수, 등급별 분포, 알림 통계, 기상 요약)
- 시간별 위험도 추이 차트
- 실시간 알림 패널
- 히트맵 (지도 시각화용 위치+위험도 데이터)

## 프로젝트 구조

```
maeul-ansimi-backend/
├── config/                    # Django 프로젝트 설정
│   ├── settings/
│   │   ├── base.py            # 공통 설정 (DRF, Celery, 캐시)
│   │   ├── local.py           # 개발 환경
│   │   └── production.py      # 운영 환경
│   ├── urls.py                # 루트 URL
│   └── celery.py              # Celery 앱
├── apps/
│   ├── elders/                # 대상자 관리
│   ├── risk/                  # 위험도 분석
│   ├── weather/               # 기상 데이터
│   ├── alerts/                # 알림 관리
│   ├── dashboard/             # 대시보드
│   └── ai/                    # AI 엔진
├── common/                    # 공통 모듈 (pagination, exceptions, cache)
├── tasks/                     # Celery 비동기 태스크
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## 시작하기

### 사전 요구사항

- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- 공공데이터포털 API 인증키 ([data.go.kr](https://data.go.kr))

### 환경 설정

```bash
# 저장소 클론
git clone <repository-url>
cd maeul-ansimi-backend

# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt

# 환경변수 설정
cp .env.example .env
# .env 파일을 열어 값을 수정하세요
```

### 주요 환경변수

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SECRET_KEY` | Django 시크릿 키 | (필수) |
| `DATABASE_URL` | PostgreSQL 연결 URL | `postgresql://maeul:maeul@localhost:5432/maeul_ansimi` |
| `REDIS_URL` | Redis 연결 URL | `redis://localhost:6379/0` |
| `DATA_GO_KR_API_KEY` | 공공데이터포털 API 키 | (필수) |
| `CORS_ORIGINS` | 허용 프론트엔드 Origin | `http://localhost:3000` |
| `KAKAO_REST_API_KEY` | 카카오 알림톡 API 키 | (선택) |

### 데이터베이스 및 서버 실행

```bash
# DB 마이그레이션
python manage.py migrate

# 시드 데이터 생성 (개발/테스트용)
python manage.py seed_elders     # 청양군 8개 읍면 300명 테스트 대상자
python manage.py seed_weather    # 기상 시나리오 데이터
python manage.py seed_risk       # 초기 위험도 계산

# 개발 서버 실행
python manage.py runserver
```

### Celery 워커 실행 (별도 터미널)

```bash
# 태스크 워커
celery -A config worker -l info

# 스케줄러 (주기적 태스크 실행)
celery -A config beat -l info
```

### Docker로 실행

```bash
docker-compose up -d
```

Django + PostgreSQL + Redis + Celery Worker + Celery Beat가 한번에 실행됩니다.

## API 엔드포인트

### 대상자 관리 — `/api/elders/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/elders/` | 목록 조회 (필터: level, region, disease, search) |
| GET | `/api/elders/{id}/` | 상세 조회 |
| POST | `/api/elders/` | 등록 |
| PATCH | `/api/elders/{id}/` | 수정 (변경 시 위험도 자동 재계산) |
| DELETE | `/api/elders/{id}/` | 소프트 삭제 |

### 위험도 — `/api/risk/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/risk/current/` | 전체 대상자 최신 위험도 |
| GET | `/api/risk/elder/{id}/` | 개별 상세 (하위점수 + 조치 권고) |
| GET | `/api/risk/elder/{id}/history/` | 이력 (period: 24h/7d/30d) |
| GET | `/api/risk/summary/` | 등급별 통계 |
| GET | `/api/risk/heatmap/` | 지도 히트맵 데이터 |

### 기상 — `/api/weather/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/weather/current/` | 현재 기상 + 활성 특보 |
| GET | `/api/weather/forecast/` | 72시간 + 주간 예보 |
| GET | `/api/weather/alerts/` | 발효중 기상특보 목록 |
| GET | `/api/weather/air-quality/` | 실시간 대기질 |

### 알림 — `/api/alerts/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/alerts/` | 알림 이력 (필터: elder_id, type, status, period) |
| POST | `/api/alerts/{id}/respond/` | 알림 응답 처리 |
| GET | `/api/alerts/stats/` | 알림 통계 |

### 대시보드 — `/api/dashboard/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | `/api/dashboard/overview/` | 종합 현황 |
| GET | `/api/dashboard/charts/` | 시간별 차트 (period: 24h/7d/30d) |
| GET | `/api/dashboard/recent-alerts/` | 최근 알림 10건 |

### AI — `/api/ai/`

| Method | Endpoint | 설명 |
|--------|----------|------|
| POST | `/api/ai/calculate-risk/` | 위험도 수동 재계산 트리거 |
| GET | `/api/ai/feature-importance/{id}/` | 요인별 기여도 분석 |
| GET | `/api/ai/model-info/` | AI 모델 정보 |

## Celery 스케줄 태스크

| 태스크 | 주기 | 설명 |
|--------|------|------|
| `fetch_weather_observation` | 30분 | 기상청 초단기실황 수집 |
| `fetch_weather_forecast` | 3시간 | 기상청 단기예보 수집 |
| `fetch_weather_alert` | 10분 | 기상특보 수집 (변경 시 위험도 즉시 재계산) |
| `fetch_air_quality` | 1시간 | 에어코리아 대기오염 수집 |
| `calculate_all_risk` | 1시간 | 전체 대상자 위험도 산출 → 알림 자동 생성 |
| `cleanup_old_data` | 매일 03:00 | 30일 초과 기상 데이터 정리 |

## 테스트

```bash
# 전체 테스트 실행
python manage.py test

# 커버리지 측정
coverage run manage.py test
coverage report
```

## 데모 시나리오

시나리오별 시연을 위한 management command가 제공됩니다.

```bash
python manage.py run_demo
```

- **폭염 시나리오**: 체감온도 38도 → 심장질환 대상자 심각 등급 → 긴급출동 알림
- **한파 시나리오**: 체감온도 -15도 → 심뇌혈관 위험 상승
- **호우 시나리오**: 시간당 50mm 강수 → 침수위험 지역 대상자 경계
- **미세먼지 시나리오**: PM2.5 100μg/m³ → 호흡기 질환 대상자 경계

## 라이선스

이 프로젝트는 충남 청양군 고령 독거노인 AI 안전관리 플랫폼 사업의 일환으로 개발되었습니다.
