# 학습 도우미 인증 플로우 API 서버

GPTs Actions와 연동되는 할 일 관리 API 서버입니다. 사용자가 챗봇 대화에 업로드한 인증 이미지를 챗봇이 판정하여 서버의 할 일을 완료(승인)로 전환하는 흐름을 구현합니다.

## 기술 스택

- Python 3.11
- Flask
- SQLAlchemy
- PostgreSQL
- Alembic (마이그레이션)
- Gunicorn (프로덕션 서버)

## 프로젝트 구조

```
.
├── app.py                    # 메인 Flask 앱
├── requirements.txt          # Python 의존성
├── alembic.ini              # Alembic 설정
├── migrations/              # 데이터베이스 마이그레이션
├── app/
│   ├── __init__.py
│   └── workers/
│       └── expire_jobs.py   # 만료 작업 워커
├── Dockerfile               # Docker 이미지 빌드
├── render.yaml             # Render 배포 설정
└── README.md
```

## 로컬 개발 환경 설정

### 1. 필요한 소프트웨어 설치

- Python 3.11 이상
- PostgreSQL
- Git

### 2. 저장소 클론 및 의존성 설치

```bash
# 가상환경 생성 및 활성화
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 의존성 설치
pip install -r requirements.txt
```

### 3. 데이터베이스 설정

```bash
# PostgreSQL에 데이터베이스 생성
createdb study_assistant

# 또는 psql로 접속하여
psql postgres
CREATE DATABASE study_assistant;
\q
```

### 4. 환경변수 설정

`.env` 파일을 생성하고 다음 내용을 입력하세요:

```bash
cp .env.example .env
```

`.env` 파일을 편집하여 실제 값으로 변경:

```
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/study_assistant
API_KEY=your-secret-api-key
CRON_TOKEN=your-secret-cron-token
FLASK_ENV=development
```

### 5. 데이터베이스 마이그레이션 실행

```bash
# Alembic 초기화 (처음 한 번만)
alembic init migrations  # 이미 migrations 폴더가 있으면 생략

# 마이그레이션 생성
alembic revision --autogenerate -m "Initial migration"

# 마이그레이션 적용
alembic upgrade head
```

### 6. 서버 실행

```bash
# 개발 모드
python app.py

# 또는 Flask CLI 사용
export FLASK_APP=app.py
flask run

# 프로덕션 모드 (Gunicorn)
gunicorn --bind 0.0.0.0:5000 "app:create_app()"
```

서버는 `http://localhost:5000`에서 실행됩니다.

## API 엔드포인트

### 인증

모든 API 엔드포인트는 `X-API-Key` 헤더가 필요합니다 (내부 엔드포인트 제외).

```
X-API-Key: your-api-key
```

### 사용자 관리

#### 사용자 생성
```
POST /v1/users
Content-Type: application/json

{
  "external_user_id": "user123",
  "tz": "Asia/Seoul"  // 선택사항
}
```

### 할 일 관리

#### 할 일 생성
```
POST /v1/tasks
Content-Type: application/json

{
  "user_id": "uuid-here",
  "title": "수능특강 물리1 p.10~20",
  "verify_method": "해당 페이지 풀이 촬영",
  "due_at_iso": "2024-12-31T23:59:59Z"
}
```

#### 할 일 목록 조회
```
GET /v1/tasks?user_id=uuid&state=PENDING&q=물리
```

쿼리 파라미터:
- `user_id` (필수): 사용자 UUID
- `state` (선택): PENDING, APPROVED, EXPIRED
- `q` (선택): 제목 검색
- `due_before` (선택): ISO 8601 datetime
- `due_after` (선택): ISO 8601 datetime

#### 인증 판정 시도
```
POST /v1/tasks/{task_id}/verify-attempt
Content-Type: application/json

{
  "proof_url": "https://r2/.../image.jpg",
  "verdict": true,
  "score": 0.92,
  "reasons": "p.10~20 범위와 일치, 이름 표기 확인",
  "raw_features": {"pages": [10, 11, 12], "found_keywords": ["물리1", "p.10"]}
}
```

### 내부 엔드포인트

#### 만료 작업 처리
```
POST /v1/internal/cron/expire
Authorization: Bearer your-cron-token
```

## Render 배포 방법

### 1. Render 계정 생성 및 프로젝트 연결

1. [Render](https://render.com)에 가입
2. GitHub 저장소와 연결
3. 새 Web Service 생성

### 2. 환경변수 설정

Render 대시보드에서 다음 환경변수를 설정:

- `DATABASE_URL`: Render PostgreSQL Add-on의 연결 문자열 (자동 생성됨)
- `API_KEY`: GPTs Actions에서 사용할 API 키
- `CRON_TOKEN`: 내부 크론 엔드포인트 보호용 토큰
- `FLASK_ENV`: `production`

### 3. PostgreSQL 데이터베이스 생성

1. Render 대시보드에서 "New +" → "PostgreSQL" 선택
2. 데이터베이스 이름: `study-assistant-db`
3. `render.yaml`에서 자동으로 연결됨

### 4. 배포 설정

#### 방법 1: render.yaml 사용 (권장)

1. 저장소 루트에 `render.yaml`이 있는지 확인
2. Render 대시보드에서 "New +" → "Blueprint" 선택
3. GitHub 저장소 연결
4. Render가 자동으로 `render.yaml`을 읽어 서비스 생성

#### 방법 2: 수동 배포

**Web Service 설정:**
- Build Command: `pip install -r requirements.txt && alembic upgrade head`
- Start Command: `gunicorn --bind 0.0.0.0:10000 --workers 2 --timeout 120 "app:create_app()"`
- Environment: `Python 3`
- Health Check Path: `/`

**Background Worker 설정:**
- Type: `Background Worker`
- Build Command: `pip install -r requirements.txt`
- Start Command: `python -m app.workers.expire_jobs`
- Environment: `Python 3`

### 5. 마이그레이션 실행

배포 후 첫 실행 시 `alembic upgrade head`가 자동으로 실행됩니다. 수동으로 실행하려면:

```bash
# Render Shell에서
alembic upgrade head
```

### 6. 배포 확인

1. Web Service URL 확인: `https://your-service.onrender.com`
2. 헬스 체크: `curl https://your-service.onrender.com/`
3. API 테스트:
   ```bash
   curl -X POST https://your-service.onrender.com/v1/users \
     -H "X-API-Key: your-api-key" \
     -H "Content-Type: application/json" \
     -d '{"external_user_id": "test123"}'
   ```

## Docker 배포 방법

### 1. Docker 이미지 빌드

```bash
docker build -t study-assistant-api .
```

### 2. Docker 컨테이너 실행

```bash
docker run -d \
  -p 5000:5000 \
  -e DATABASE_URL=postgresql+psycopg://user:pass@host:5432/db \
  -e API_KEY=your-api-key \
  -e CRON_TOKEN=your-cron-token \
  -e FLASK_ENV=production \
  --name study-assistant \
  study-assistant-api
```

### 3. Docker Compose 사용 (선택사항)

`docker-compose.yml` 파일을 생성하여 사용할 수 있습니다.

## 개발 팁

### 마이그레이션 생성

```bash
# 모델 변경 후
alembic revision --autogenerate -m "Description"
alembic upgrade head
```

### 데이터베이스 초기화

```bash
# 주의: 모든 데이터 삭제
alembic downgrade base
alembic upgrade head
```

### 로컬 테스트

```bash
# API 테스트
curl -X POST http://localhost:5000/v1/users \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{"external_user_id": "test123"}'
```

## 문제 해결

### 데이터베이스 연결 오류

- `DATABASE_URL` 환경변수가 올바른지 확인
- PostgreSQL 서버가 실행 중인지 확인
- 방화벽 설정 확인

### 마이그레이션 오류

```bash
# 마이그레이션 상태 확인
alembic current

# 특정 버전으로 롤백
alembic downgrade <revision>
```

### 워커가 실행되지 않음

- `EXPIRE_INTERVAL_SECONDS` 환경변수 확인
- Render 로그에서 오류 메시지 확인

## 라이선스

MIT

