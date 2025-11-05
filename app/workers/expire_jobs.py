"""
만료 작업 처리 워커
주기적으로 마감된 작업을 EXPIRED로 전환
"""
import os
import sys
import time
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from uuid import uuid4

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql+psycopg://localhost/study_assistant')
CRON_TOKEN = os.getenv('CRON_TOKEN', 'changeme-cron')
INTERVAL_SECONDS = int(os.getenv('EXPIRE_INTERVAL_SECONDS', '300'))  # 기본 5분

Base = declarative_base()
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# Task 모델 정의 (app.py와 동일)
class Task(Base):
    __tablename__ = 'tasks'
    
    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(PGUUID(as_uuid=True), ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    title = Column(Text, nullable=False)
    verify_method = Column(Text, nullable=False)
    due_at = Column(DateTime(timezone=True), nullable=False)
    state = Column(String(20), nullable=False, default='PENDING')
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))


def expire_overdue_tasks(db):
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


def run_expire_job():
    """만료 작업 실행"""
    db = SessionLocal()
    try:
        processed = expire_overdue_tasks(db)
        print(f"[{datetime.now(timezone.utc).isoformat()}] Expired {processed} tasks")
    except Exception as e:
        print(f"[{datetime.now(timezone.utc).isoformat()}] Error: {str(e)}")
        db.rollback()
    finally:
        db.close()


if __name__ == '__main__':
    print(f"Starting expire worker (interval: {INTERVAL_SECONDS}s)")
    while True:
        try:
            run_expire_job()
            time.sleep(INTERVAL_SECONDS)
        except KeyboardInterrupt:
            print("Stopping worker...")
            break
        except Exception as e:
            print(f"Fatal error: {str(e)}")
            time.sleep(INTERVAL_SECONDS)
