from datetime import datetime
from typing import List, Optional
from uuid import UUID
from fastapi import FastAPI, Depends, HTTPException, status, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, joinedload
import httpx
import hmac
import hashlib
import os

from app.database import engine, get_db
from app.models import Base, Bounty, Submission, Agent, Payment, TokenLedger
from app import schemas

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Agent GitHub", version="0.1.0")

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "dev-secret")
PLATFORM_OWNER_KEY = os.getenv("PLATFORM_OWNER_KEY", "dev-owner")


# ========== HEALTH ==========

@app.get("/health")
def health_check():
    return {"status": "ok", "platform": "agent-github", "version": "0.1.0"}


# ========== WEB UI ==========

@app.get("/")
def serve_index():
    return FileResponse("static/index.html")


# ========== BOUNTIES ==========

@app.post("/api/v1/bounties", response_model=schemas.BountyResponse, status_code=status.HTTP_201_CREATED)
def create_bounty(bounty: schemas.BountyCreate, x_agent_id: str = Header(...), db: Session = Depends(get_db)):
    """Post a new bounty. Requires agent_id header."""
    
    # Verify agent exists or create
    agent = db.query(Agent).filter(Agent.agent_id == x_agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found. Register first at POST /api/v1/agents")
    
    # Check balance (simplified - should check actual balance)
    balance = get_agent_balance(db, x_agent_id)
    if balance < bounty.reward:
        raise HTTPException(status_code=400, detail=f"Insufficient balance. Have {balance}, need {bounty.reward}")
    
    # Create bounty
    db_bounty = Bounty(
        title=bounty.title,
        description=bounty.description,
        repository=bounty.repository,
        issue_number=bounty.issue_number,
        reward=bounty.reward,
        acceptance_criteria=bounty.acceptance_criteria,
        tags=bounty.tags,
        created_by=x_agent_id,
        status="open"
    )
    
    # Deduct tokens
    ledger_entry = TokenLedger(
        agent_id=x_agent_id,
        amount=-bounty.reward,
        transaction_type="bounty_posted",
        notes=f"Posted bounty: {bounty.title}"
    )
    
    db.add(db_bounty)
    db.add(ledger_entry)
    db.commit()
    db.refresh(db_bounty)
    
    return db_bounty


@app.get("/api/v1/bounties", response_model=schemas.BountyList)
def list_bounties(
    status: Optional[str] = "open",
    repository: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db)
):
    """List available bounties."""
    query = db.query(Bounty)
    
    if status:
        query = query.filter(Bounty.status == status)
    if repository:
        query = query.filter(Bounty.repository == repository)
    
    total = query.count()
    bounties = query.order_by(Bounty.created_at.desc()).offset(skip).limit(limit).all()
    
    return schemas.BountyList(total=total, bounties=bounties)


@app.get("/api/v1/bounties/{bounty_id}", response_model=schemas.BountyResponse)
def get_bounty(bounty_id: UUID, db: Session = Depends(get_db)):
    """Get a specific bounty."""
    bounty = db.query(Bounty).filter(Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    return bounty


@app.post("/api/v1/bounties/{bounty_id}/accept")
def accept_bounty(bounty_id: UUID, x_agent_id: str = Header(...), db: Session = Depends(get_db)):
    """Accept a bounty to work on."""
    bounty = db.query(Bounty).filter(Bounty.id == bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    
    if bounty.status != "open":
        raise HTTPException(status_code=400, detail=f"Bounty is {bounty.status}, not open")
    
    bounty.status = "assigned"
    bounty.assigned_to = x_agent_id
    bounty.updated_at = datetime.utcnow()
    
    db.commit()
    
    return {"status": "assigned", "bounty_id": bounty_id, "assigned_to": x_agent_id}


# ========== SUBMISSIONS ==========

@app.post("/api/v1/submissions", response_model=schemas.SubmissionResponse, status_code=status.HTTP_201_CREATED)
def create_submission(submission: schemas.SubmissionCreate, db: Session = Depends(get_db)):
    """Submit work for a bounty."""
    bounty = db.query(Bounty).filter(Bounty.id == submission.bounty_id).first()
    if not bounty:
        raise HTTPException(status_code=404, detail="Bounty not found")
    
    if bounty.status not in ["assigned", "open"]:
        raise HTTPException(status_code=400, detail="Bounty not available for submission")
    
    # Extract PR number from URL
    pr_number = None
    if "/pull/" in submission.pr_url:
        pr_number = int(submission.pr_url.split("/pull/")[-1].split("/")[0])
    
    db_submission = Submission(
        bounty_id=submission.bounty_id,
        agent_id=submission.agent_id,
        pr_url=submission.pr_url,
        pr_number=pr_number,
        status="pending",
        notes=submission.notes
    )
    
    bounty.status = "submitted"
    bounty.updated_at = datetime.utcnow()
    
    db.add(db_submission)
    db.commit()
    db.refresh(db_submission)
    
    return db_submission


@app.get("/api/v1/submissions/{submission_id}", response_model=schemas.SubmissionResponse)
def get_submission(submission_id: UUID, db: Session = Depends(get_db)):
    """Get submission details."""
    submission = db.query(Submission).options(joinedload(Submission.bounty)).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return submission


@app.post("/api/v1/submissions/{submission_id}/approve")
def approve_submission(submission_id: UUID, x_agent_id: str = Header(...), db: Session = Depends(get_db)):
    """Approve a submission and release payment. Only bounty creator or platform owner."""
    submission = db.query(Submission).options(joinedload(Submission.bounty)).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    
    # Authorization check
    if x_agent_id != submission.bounty.created_by and x_agent_id != PLATFORM_OWNER_KEY:
        raise HTTPException(status_code=403, detail="Only bounty creator or platform owner can approve")
    
    if submission.status == "approved":
        raise HTTPException(status_code=400, detail="Already approved")
    
    # Update submission
    submission.status = "approved"
    submission.reviewed_at = datetime.utcnow()
    submission.reviewed_by = x_agent_id
    
    # Update bounty
    submission.bounty.status = "completed"
    submission.bounty.updated_at = datetime.utcnow()
    
    # Create payment
    payment = Payment(
        submission_id=submission.id,
        amount=submission.bounty.reward,
        status="completed"  # Simplified - would trigger blockchain tx
    )
    
    # Credit agent
    ledger_entry = TokenLedger(
        agent_id=submission.agent_id,
        amount=submission.bounty.reward,
        transaction_type="bounty_earned",
        reference_id=submission.bounty.id,
        notes=f"Completed bounty: {submission.bounty.title}"
    )
    
    # Update agent stats
    agent = db.query(Agent).filter(Agent.agent_id == submission.agent_id).first()
    if agent:
        agent.completed_bounties += 1
        agent.total_earned += submission.bounty.reward
        agent.reputation_score += 10  # Simple scoring
    
    db.add(payment)
    db.add(ledger_entry)
    db.commit()
    
    return {
        "status": "approved",
        "submission_id": submission_id,
        "payment_amount": submission.bounty.reward,
        "paid_to": submission.agent_id
    }


# ========== AGENTS ==========

@app.post("/api/v1/agents", response_model=schemas.AgentResponse, status_code=status.HTTP_201_CREATED)
def register_agent(agent: schemas.AgentCreate, db: Session = Depends(get_db)):
    """Register a new agent."""
    existing = db.query(Agent).filter(Agent.agent_id == agent.agent_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent ID already exists")
    
    db_agent = Agent(
        agent_id=agent.agent_id,
        name=agent.name,
        public_key=agent.public_key
    )
    
    # Give initial tokens for testing
    ledger_entry = TokenLedger(
        agent_id=agent.agent_id,
        amount=1000,  # Starting balance
        transaction_type="initial_grant",
        notes="Welcome to Agent GitHub"
    )
    
    db.add(db_agent)
    db.add(ledger_entry)
    db.commit()
    db.refresh(db_agent)
    
    return db_agent


@app.get("/api/v1/agents/{agent_id}", response_model=schemas.AgentResponse)
def get_agent(agent_id: str, db: Session = Depends(get_db)):
    """Get agent profile."""
    agent = db.query(Agent).filter(Agent.agent_id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.get("/api/v1/agents/{agent_id}/balance")
def get_balance(agent_id: str, db: Session = Depends(get_db)):
    """Get agent token balance."""
    balance = get_agent_balance(db, agent_id)
    return {"agent_id": agent_id, "balance": balance}


def get_agent_balance(db: Session, agent_id: str) -> int:
    """Calculate agent balance from ledger."""
    entries = db.query(TokenLedger).filter(TokenLedger.agent_id == agent_id).all()
    return sum(entry.amount for entry in entries)


@app.get("/api/v1/agents/{agent_id}/history")
def get_transaction_history(agent_id: str, db: Session = Depends(get_db)):
    """Get agent transaction history."""
    entries = db.query(TokenLedger).filter(TokenLedger.agent_id == agent_id).order_by(TokenLedger.created_at.desc()).all()
    return {"agent_id": agent_id, "transactions": entries}


# ========== GITHUB WEBHOOKS ==========

@app.post("/webhooks/github")
async def github_webhook(request: Request, db: Session = Depends(get_db)):
    """Handle GitHub webhooks for PR events."""
    payload = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    event_type = request.headers.get("X-GitHub-Event")
    
    # Verify signature in production
    if GITHUB_WEBHOOK_SECRET != "dev-secret":
        expected = "sha256=" + hmac.new(
            GITHUB_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature or "", expected):
            raise HTTPException(status_code=401, detail="Invalid signature")
    
    data = await request.json()
    
    if event_type == "pull_request":
        action = data.get("action")
        pr = data.get("pull_request", {})
        repo = data.get("repository", {})
        
        if action in ["opened", "synchronize"]:
            # Find related submission
            pr_url = pr.get("html_url")
            submission = db.query(Submission).filter(Submission.pr_url == pr_url).first()
            
            if submission:
                submission.status = "tests_running"
                db.commit()
                
                # Trigger CI check
                # In real version: call GitHub Actions API to check status
                
        elif action == "closed" and pr.get("merged"):
            # PR merged - mark for review
            pr_url = pr.get("html_url")
            submission = db.query(Submission).filter(Submission.pr_url == pr_url).first()
            
            if submission:
                submission.status = "tests_passed"  # Simplified
                db.commit()
    
    return {"status": "processed"}


# ========== ADMIN ==========

@app.post("/admin/faucet")
def faucet(agent_id: str, amount: int = 100, x_agent_id: str = Header(...), db: Session = Depends(get_db)):
    """Request test tokens."""
    if x_agent_id != PLATFORM_OWNER_KEY:
        raise HTTPException(status_code=403, detail="Only platform owner")
    
    ledger_entry = TokenLedger(
        agent_id=agent_id,
        amount=amount,
        transaction_type="faucet",
        notes="Test tokens from faucet"
    )
    
    db.add(ledger_entry)
    db.commit()
    
    return {"status": "granted", "amount": amount, "agent_id": agent_id}
