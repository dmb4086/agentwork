from datetime import datetime
from enum import Enum
from typing import Optional, List
from uuid import UUID, uuid4
from pydantic import BaseModel


class BountyStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class SubmissionStatus(str, Enum):
    PENDING = "pending"
    TESTS_RUNNING = "tests_running"
    TESTS_PASSED = "tests_passed"
    TESTS_FAILED = "tests_failed"
    APPROVED = "approved"
    REJECTED = "rejected"


# Bounty Schemas
class BountyCreate(BaseModel):
    title: str
    description: str
    repository: str
    issue_number: Optional[int] = None
    reward: int
    acceptance_criteria: List[str]
    tags: List[str] = []


class BountyResponse(BaseModel):
    id: UUID
    title: str
    description: str
    repository: str
    issue_number: Optional[int]
    reward: int
    status: BountyStatus
    acceptance_criteria: List[str]
    tags: List[str]
    created_by: str
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime


class BountyList(BaseModel):
    total: int
    bounties: List[BountyResponse]


# Submission Schemas
class SubmissionCreate(BaseModel):
    bounty_id: UUID
    agent_id: str
    pr_url: str
    notes: Optional[str] = None


class SubmissionResponse(BaseModel):
    id: UUID
    bounty_id: UUID
    agent_id: str
    pr_url: str
    pr_number: Optional[int]
    status: SubmissionStatus
    test_results: Optional[dict]
    notes: Optional[str]
    created_at: datetime
    reviewed_at: Optional[datetime]
    reviewed_by: Optional[str]


# Agent Schemas
class AgentCreate(BaseModel):
    agent_id: str
    name: str
    public_key: str


class AgentResponse(BaseModel):
    agent_id: str
    name: str
    public_key: str
    reputation_score: int
    completed_bounties: int
    total_earned: int
    created_at: datetime


# Payment Schemas
class PaymentResponse(BaseModel):
    id: UUID
    submission_id: UUID
    amount: int
    status: str
    transaction_hash: Optional[str]
    created_at: datetime
