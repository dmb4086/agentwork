from datetime import datetime
from uuid import uuid4
from sqlalchemy import Column, String, Integer, DateTime, Text, JSON, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class BountyStatus(str):
    OPEN = "open"
    ASSIGNED = "assigned" 
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SubmissionStatus(str):
    PENDING = "pending"
    TESTS_RUNNING = "tests_running"
    TESTS_PASSED = "tests_passed"
    TESTS_FAILED = "tests_failed"
    APPROVED = "approved"
    REJECTED = "rejected"


class Bounty(Base):
    __tablename__ = "bounties"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=False)
    repository = Column(String(255), nullable=False, index=True)
    issue_number = Column(Integer, nullable=True)
    reward = Column(Integer, nullable=False)  # in tokens
    status = Column(String(20), default="open", index=True)
    acceptance_criteria = Column(ARRAY(String), default=[])
    tags = Column(ARRAY(String), default=[])
    created_by = Column(String(255), nullable=False)
    assigned_to = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    submissions = relationship("Submission", back_populates="bounty")


class Submission(Base):
    __tablename__ = "submissions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    bounty_id = Column(UUID(as_uuid=True), ForeignKey("bounties.id"), index=True)
    agent_id = Column(String(255), nullable=False, index=True)
    pr_url = Column(String(500), nullable=False)
    pr_number = Column(Integer, nullable=True)
    status = Column(String(20), default="pending", index=True)
    test_results = Column(JSON, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String(255), nullable=True)
    
    bounty = relationship("Bounty", back_populates="submissions")
    payment = relationship("Payment", back_populates="submission", uselist=False)


class Agent(Base):
    __tablename__ = "agents"
    
    agent_id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    public_key = Column(String(255), nullable=False, unique=True)
    reputation_score = Column(Integer, default=0)
    completed_bounties = Column(Integer, default=0)
    total_earned = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Payment(Base):
    __tablename__ = "payments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    submission_id = Column(UUID(as_uuid=True), ForeignKey("submissions.id"), unique=True)
    amount = Column(Integer, nullable=False)
    status = Column(String(20), default="pending", index=True)
    transaction_hash = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    submission = relationship("Submission", back_populates="payment")


class TokenLedger(Base):
    __tablename__ = "token_ledger"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(String(255), nullable=False, index=True)
    amount = Column(Integer, nullable=False)  # positive = credit, negative = debit
    transaction_type = Column(String(50), nullable=False)  # "bounty_posted", "bounty_earned", "transfer"
    reference_id = Column(UUID(as_uuid=True), nullable=True)  # bounty_id or submission_id
    created_at = Column(DateTime, default=datetime.utcnow)
    notes = Column(Text, nullable=True)
