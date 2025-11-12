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

## 환경변수 빠른 참조

| 환경변수 | 필수 여부 | 기본값 | 설명 |
|---------|---------|--------|------|
| `DATABASE_URL` | ✅ 필수 | 없음 | PostgreSQL 연결 문자열 |
| `API_KEY` | ✅ 필수 | 없음 | GPTs Actions 인증 키 (32자 이상 권장) |
| `CRON_TOKEN` | ✅ 필수 | 없음 | 내부 크론 토큰 (32자 이상 권장) |
| `FLASK_ENV` | 선택 | `development` | `development` 또는 `production` |
| `EXPIRE_INTERVAL_SECONDS` | 선택 | `300` | 만료 작업 체크 주기 (초) |

> 💡 **상세 설명은 아래 "환경변수 설정" 섹션을 참조하세요.**

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

#### 환경변수 상세 설명

##### 필수 환경변수

**`DATABASE_URL`** (필수)
- **설명**: PostgreSQL 데이터베이스 연결 문자열
- **형식**: `postgresql+psycopg://[사용자명]:[비밀번호]@[호스트]:[포트]/[데이터베이스명]`
- **예시**:
  - 로컬 개발: `postgresql+psycopg://postgres:mypassword@localhost:5432/study_assistant`
  - Render: Render PostgreSQL Add-on에서 자동 생성 (대시보드에서 확인 가능)
- **설정 방법**:
  - 로컬: PostgreSQL 설치 후 직접 작성
  - Render: PostgreSQL Add-on 생성 시 자동으로 환경변수에 추가됨
- **주의사항**: 
  - 비밀번호에 특수문자가 포함된 경우 URL 인코딩 필요
  - 프로덕션 환경에서는 반드시 강력한 비밀번호 사용

**`API_KEY`** (필수)
- **설명**: GPTs Actions에서 API를 호출할 때 사용하는 인증 키
- **형식**: 임의의 긴 문자열 (최소 32자 권장)
- **예시**: 
  - `sk-1234567890abcdefghijklmnopqrstuvwxyz`
  - `my-super-secret-api-key-for-gpts-actions-2024`
- **생성 방법**:
  ```bash
  # Python으로 랜덤 키 생성
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  
  # 또는 OpenSSL 사용
  openssl rand -hex 32
  ```
- **사용처**: 
  - 모든 공용 API 엔드포인트 (`/v1/users`, `/v1/tasks` 등)의 `X-API-Key` 헤더
  - GPTs Actions 설정에서 이 키를 입력하여 API 인증
- **보안**: 
  - 절대 코드에 하드코딩하지 않기
  - Git에 커밋하지 않기 (`.env`는 `.gitignore`에 포함됨)
  - 각 환경별로 다른 키 사용 권장

**`CRON_TOKEN`** (필수)
- **설명**: 내부 크론 엔드포인트(`/v1/internal/cron/expire`) 보호용 Bearer 토큰
- **형식**: 임의의 긴 문자열 (최소 32자 권장)
- **예시**:
  - `cron-secret-token-2024-abcdef123456`
  - `internal-expire-worker-token-xyz789`
- **생성 방법**: `API_KEY`와 동일하게 랜덤 문자열 생성
- **사용처**: 
  - Background Worker가 만료 작업을 처리할 때 사용 (현재는 HTTP 호출 대신 직접 DB 접근)
  - 향후 외부 크론 서비스(예: cron-job.org)에서 호출 시 사용
- **보안**: 
  - `API_KEY`와 별도로 다른 값 사용
  - 외부에 노출되지 않도록 주의

##### 선택적 환경변수

**`FLASK_ENV`** (선택, 기본값: `development`)
- **설명**: Flask 애플리케이션 실행 환경
- **가능한 값**:
  - `development`: 개발 모드 (디버그 모드, 상세한 로그 출력)
  - `production`: 프로덕션 모드 (최적화된 설정)
- **예시**: `FLASK_ENV=production`
- **설정 권장**:
  - 로컬 개발: `development`
  - Render 배포: `production`
- **영향**:
  - 개발 모드: SQLAlchemy 쿼리 로그 출력, 자동 리로드
  - 프로덕션 모드: 성능 최적화, 에러 페이지 단순화

**`EXPIRE_INTERVAL_SECONDS`** (선택, 기본값: `300`)
- **설명**: Background Worker가 만료 작업을 처리하는 주기 (초 단위)
- **형식**: 정수 (초 단위)
- **예시**: 
  - `300` (5분마다 실행)
  - `600` (10분마다 실행)
  - `60` (1분마다 실행 - 빈번한 체크 필요 시)
- **권장값**: 
  - 일반적인 용도: `300` (5분)
  - 실시간성이 중요한 경우: `60` (1분)
  - 리소스 절약이 필요한 경우: `600` (10분)
- **사용처**: `app/workers/expire_jobs.py`에서 사용
- **주의사항**: 너무 짧은 간격(예: 10초 이하)은 데이터베이스 부하를 증가시킬 수 있음

#### 환경변수 설정 예시

**로컬 개발 환경 (.env 파일)**
```bash
# 데이터베이스 (로컬 PostgreSQL)
DATABASE_URL=postgresql+psycopg://postgres:postgres123@localhost:5432/study_assistant

# API 인증 (GPTs Actions에서 사용)
API_KEY=dev-api-key-1234567890abcdefghijklmnopqrstuvwxyz

# 내부 크론 토큰
CRON_TOKEN=dev-cron-token-abcdef1234567890ghijklmnopqrstuv

# 개발 모드
FLASK_ENV=development

# 만료 체크 주기 (선택사항)
EXPIRE_INTERVAL_SECONDS=300
```

**Render 프로덕션 환경 (대시보드에서 설정)**
```
DATABASE_URL=<Render PostgreSQL Add-on에서 자동 생성>
API_KEY=<강력한 랜덤 문자열 생성>
CRON_TOKEN=<강력한 랜덤 문자열 생성 (API_KEY와 다른 값)>
FLASK_ENV=production
EXPIRE_INTERVAL_SECONDS=300
```

#### 환경변수 확인 방법

**로컬 환경에서 확인:**
```bash
# Python으로 확인
python -c "import os; print(os.getenv('DATABASE_URL'))"

# 또는 .env 파일 직접 확인
cat .env
```

**Render 환경에서 확인:**
1. Render 대시보드 → 해당 서비스 선택
2. "Environment" 탭 클릭
3. 환경변수 목록 확인 및 수정 가능

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

#### 자동 설정되는 환경변수

- **`DATABASE_URL`**: Render PostgreSQL Add-on 생성 시 자동으로 설정됩니다. `render.yaml`에서 `fromDatabase`로 연결됩니다.

#### 수동 설정이 필요한 환경변수

1. **`API_KEY`** (필수)
   - Render 대시보드 → "Environment" 탭 → "Add Environment Variable" 클릭
   - Key: `API_KEY`
   - Value: 안전한 랜덤 문자열 (최소 32자)
   - 생성 방법:
     ```bash
     # 로컬에서 생성 후 복사
     python -c "import secrets; print(secrets.token_urlsafe(32))"
     ```
   - 예시: `sk_live_abc123xyz789...` (32자 이상)

2. **`CRON_TOKEN`** (필수)
   - Key: `CRON_TOKEN`
   - Value: `API_KEY`와 다른 안전한 랜덤 문자열
   - 생성 방법: `API_KEY`와 동일
   - 예시: `cron_internal_token_xyz789...` (32자 이상)

3. **`FLASK_ENV`** (권장)
   - Key: `FLASK_ENV`
   - Value: `production`
   - 프로덕션 환경에서는 반드시 `production`으로 설정

4. **`EXPIRE_INTERVAL_SECONDS`** (선택)
   - Key: `EXPIRE_INTERVAL_SECONDS`
   - Value: `300` (기본값, 5분)
   - 만료 작업 체크 주기를 변경하려면 설정

#### 환경변수 설정 순서

1. Render 대시보드 접속
2. Web Service 선택 (또는 새로 생성)
3. 좌측 메뉴에서 "Environment" 클릭
4. "Add Environment Variable" 버튼 클릭
5. 각 환경변수 입력 후 "Save Changes" 클릭
6. 서비스 재배포 (자동 재배포되거나 수동으로 재배포 필요)

#### 보안 권장사항

- ✅ 각 환경변수는 서로 다른 랜덤 값 사용
- ✅ 최소 32자 이상의 긴 문자열 사용
- ✅ 정기적으로 키 로테이션 (특히 프로덕션 환경)
- ❌ 예측 가능한 값 사용 금지 (예: `password123`, `test`)
- ❌ Git 저장소에 커밋하지 않기

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

