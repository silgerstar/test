"""
학습 도우미 인증 플로우 기반 API 서버
Flask + SQLAlchemy + PostgreSQL
"""

import os
import re
from datetime import datetime, timezone
from functools import wraps
from typing import Optional, Dict, Any
from uuid import UUID, uuid4

from flask import Flask, request, jsonify
from sqlalchemy import (
    create_engine, Column, String, Text, DateTime, Boolean, Numeric,
    ForeignKey, CheckConstraint, Index, func
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID, JSONB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.exc import IntegrityError
from dateutil import parser as date_parser

# 환경변수 로드
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://localhost/study_assistant')
API_KEY = os.getenv('API_KEY', 'changeme-actions')
CRON_TOKEN = os.getenv('CRON_TOKEN', 'changeme-cron')
FLASK_ENV = os.getenv('FLASK_ENV', 'development')

# Flask 앱 생성
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# SQLAlchemy 설정
engine = create_engine(DATABASE_URL, echo=(FLASK_ENV == 'development'))
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ============================================================================
# 모델 정의
# ============================================================================

class User(Base):
    __tablename__ = 'users'
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    external_user_id = Column(Text, unique=True, nullable=False, index=True)
    tz = Column(Text, default='Asia/Seoul')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    tasks = relationship('Task', back_populates='user', cascade='all, delete-orphan')


class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(Text, nullable=False)
    verify_method = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    user = relationship('User', back_populates='tasks')
    verification_attempts = relationship('VerificationAttempt', back_populates='task', cascade='all, delete-orphan')
    
    __table_args__ = (
        CheckConstraint("state IN ('PENDING', 'APPROVED', 'EXPIRED')", name='check_task_state'),
        Index('idx_tasks_user_state', 'user_id', 'state'),
        Index('idx_tasks_user_due', 'user_id', 'due_at'),
    )


class VerificationAttempt(Base):
    __tablename__ = 'verification_attempts'
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    task_id = Column(PGUUID(as_uuid=True), ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False)
    attempted_at = Column(DateTime(timezone=True), server_default=func.now())
    proof_url = Column(Text, nullable=False)
    verdict = Column(Boolean, nullable=False)
    score = Column(Numeric(5, 2), nullable=True)
    reasons = Column(Text, nullable=True)
    raw_features = Column(JSONB, nullable=True)
    
    task = relationship('Task', back_populates='verification_attempts')

# ============================================================================
# DB 테이블 생성 (없으면 자동 생성)
#  - 이 줄은 모듈이 import 될 때 딱 한 번 실행된다.
#  - 이미 테이블이 있으면 아무것도 안 하고, 없으면 users/tasks/verification_attempts를 만든다.
# ============================================================================
Base.metadata.create_all(bind=engine)

# ============================================================================
# 인증 미들웨어
# ============================================================================

def require_api_key(f):
    """X-API-Key 헤더 검증"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key or api_key != API_KEY:
            return jsonify({'error': 'Invalid or missing API key'}), 401
        return f(*args, **kwargs)
    return decorated_function


def require_bearer_token(f):
    """Bearer 토큰 검증 (내부 엔드포인트용)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401
        token = auth_header.replace('Bearer ', '')
        if token != CRON_TOKEN:
            return jsonify({'error': 'Invalid token'}), 401
        return f(*args, **kwargs)
    return decorated_function


# ============================================================================
# 유틸리티 함수
# ============================================================================

def get_db() -> Session:
    """DB 세션 생성"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_query(q: str) -> str:
    """검색 쿼리 정규화 (공백 정규화)"""
    return re.sub(r'\s+', ' ', q.strip())


def parse_datetime(dt_str: str) -> datetime:
    """ISO 8601 datetime 파싱"""
    try:
        dt = date_parser.isoparse(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception as e:
        raise ValueError(f"Invalid datetime format: {dt_str}")


def format_datetime(dt: datetime) -> str:
    """datetime을 ISO 8601 형식으로 변환"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ============================================================================
# 서비스 함수
# ============================================================================

def expire_overdue_tasks(db: Session) -> int:
    """마감 시간이 지난 PENDING 작업을 EXPIRED로 전환"""
    now = datetime.now(timezone.utc)
    tasks = db.query(Task).filter(
        Task.state == 'PENDING',
        Task.due_at <= now
    ).all()
    
    count = 0
    for task in tasks:
        task.state = 'EXPIRED'
        task.updated_at = now
        count += 1
    
    db.commit()
    return count


# ============================================================================
# API 라우트
# ============================================================================

@app.route('/')
def health():
    """헬스 체크"""
    return jsonify({'ok': True})


@app.route('/v1/users', methods=['POST'])
@require_api_key
def create_user():
    """사용자 생성"""
    data = request.get_json() or {}
    external_user_id = data.get('external_user_id')
    tz = data.get('tz', 'Asia/Seoul')
    
    if not external_user_id:
        return jsonify({'error': 'external_user_id is required'}), 400
    
    db = next(get_db())
    try:
        user = User(external_user_id=external_user_id, tz=tz)
        db.add(user)
        db.commit()
        db.refresh(user)
        return jsonify({'user_id': str(user.id)}), 201
    except IntegrityError:
        db.rollback()
        # 이미 존재하는 사용자 조회
        user = db.query(User).filter_by(external_user_id=external_user_id).first()
        if user:
            return jsonify({'user_id': str(user.id)}), 200
        return jsonify({'error': 'Failed to create user'}), 500
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/v1/tasks', methods=['POST'])
@require_api_key
def create_task():
    """할 일 생성"""
    data = request.get_json() or {}
    user_id = data.get('user_id')
    title = data.get('title')
    verify_method = data.get('verify_method')
    due_at_iso = data.get('due_at_iso')
    
    if not all([user_id, title, verify_method, due_at_iso]):
        return jsonify({'error': 'user_id, title, verify_method, due_at_iso are required'}), 400
    
    db = next(get_db())
    try:
        user_uuid = UUID(user_id)
        due_at = parse_datetime(due_at_iso)
        
        # 사용자 존재 확인
        user = db.query(User).filter_by(id=user_uuid).first()
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        task = Task(
            user_id=user_uuid,
            title=title,
            verify_method=verify_method,
            due_at=due_at,
            state='PENDING'
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        
        return jsonify({
            'task_id': str(task.id),
            'state': task.state
        }), 201
    except ValueError as e:
        db.rollback()
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/v1/tasks', methods=['GET'])
@require_api_key
def list_tasks():
    """할 일 목록 조회"""
    user_id = request.args.get('user_id')
    state = request.args.get('state')
    q = request.args.get('q')
    due_before = request.args.get('due_before')
    due_after = request.args.get('due_after')
    
    if not user_id:
        return jsonify({'error': 'user_id is required'}), 400
    
    db = next(get_db())
    try:
        user_uuid = UUID(user_id)
        query = db.query(Task).filter_by(user_id=user_uuid)
        
        # 상태 필터
        if state:
            if state not in ['PENDING', 'APPROVED', 'EXPIRED']:
                return jsonify({'error': 'Invalid state'}), 400
            query = query.filter_by(state=state)
        
        # 제목 검색
        if q:
            normalized_q = normalize_query(q)
            query = query.filter(Task.title.ilike(f'%{normalized_q}%'))
        
        # 마감일 필터
        if due_before:
            try:
                dt = parse_datetime(due_before)
                query = query.filter(Task.due_at <= dt)
            except ValueError as e:
                return jsonify({'error': f'Invalid due_before: {str(e)}'}), 400
        
        if due_after:
            try:
                dt = parse_datetime(due_after)
                query = query.filter(Task.due_at >= dt)
            except ValueError as e:
                return jsonify({'error': f'Invalid due_after: {str(e)}'}), 400
        
        tasks = query.order_by(Task.due_at).all()
        
        items = [{
            'id': str(task.id),
            'title': task.title,
            'verify_method': task.verify_method,
            'due_at_iso': format_datetime(task.due_at),
            'state': task.state
        } for task in tasks]
        
        return jsonify({'items': items}), 200
    except ValueError as e:
        return jsonify({'error': f'Invalid user_id: {str(e)}'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/v1/tasks/<task_id>/verify-attempt', methods=['POST'])
@require_api_key
def verify_attempt(task_id: str):
    """인증 판정 시도 기록 및 상태 전환"""
    data = request.get_json() or {}
    proof_url = data.get('proof_url')
    verdict = data.get('verdict')
    score = data.get('score')
    reasons = data.get('reasons')
    raw_features = data.get('raw_features')
    
    if proof_url is None or verdict is None:
        return jsonify({'error': 'proof_url and verdict are required'}), 400
    
    if not isinstance(verdict, bool):
        return jsonify({'error': 'verdict must be boolean'}), 400
    
    db = next(get_db())
    try:
        task_uuid = UUID(task_id)
        task = db.query(Task).filter_by(id=task_uuid).first()
        
        if not task:
            return jsonify({'error': 'Task not found'}), 404
        
        # 판정 시도 로그 저장
        attempt = VerificationAttempt(
            task_id=task_uuid,
            proof_url=proof_url,
            verdict=verdict,
            score=score,
            reasons=reasons,
            raw_features=raw_features
        )
        db.add(attempt)
        
        # verdict=true면 상태를 APPROVED로 전환
        if verdict and task.state == 'PENDING':
            task.state = 'APPROVED'
            task.updated_at = datetime.now(timezone.utc)
        
        db.commit()
        db.refresh(attempt)
        
        return jsonify({
            'attempt_id': str(attempt.id),
            'task_state': task.state,
            'verdict': verdict
        }), 200
    except ValueError as e:
        db.rollback()
        return jsonify({'error': f'Invalid task_id: {str(e)}'}), 400
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


@app.route('/v1/internal/cron/expire', methods=['POST'])
@require_bearer_token
def expire_tasks():
    """만료 처리 (크론/워커용)"""
    db = next(get_db())
    try:
        processed = expire_overdue_tasks(db)
        return jsonify({'processed': processed}), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()


# ============================================================================
# 앱 초기화 및 DB 테이블 생성
# ============================================================================

def create_app():
    """Flask 앱 팩토리"""
    # 테이블 생성 (개발 환경에서만)
    if FLASK_ENV == 'development':
        Base.metadata.create_all(engine)
    return app


# ============================================================================
# 진입점
# ============================================================================

if __name__ == '__main__':
    # 개발 환경에서만 실행
    Base.metadata.create_all(engine)
    app.run(host='0.0.0.0', port=5000, debug=(FLASK_ENV == 'development'))

