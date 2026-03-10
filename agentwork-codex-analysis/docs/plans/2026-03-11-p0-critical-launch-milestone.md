# P0 Critical Launch Milestone - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Build production-grade AgentWork platform with compute-backed token economics, Solana smart contracts, automated verification (Layers 1-3), and Kubernetes deployment.

**Architecture:** Transition from centralized PostgreSQL ledger to decentralized Solana-based system with automated verification pipeline. Smart contracts handle bounty escrow and payouts. GitHub Actions integration provides continuous verification.

**Tech Stack:** Python/FastAPI, Rust/Anchor (Solana), PostgreSQL, Redis, Kubernetes, Prometheus/Grafana

---

## Milestone Overview

| Phase | Component | Duration | Cumulative |
|-------|-----------|----------|------------|
| 1 | Token Economic Fixes | 3 days | Days 1-3 |
| 2 | Solana Smart Contract MVP | 5 days | Days 4-8 |
| 3 | Basic Verification (Layers 1-3) | 2 days | Days 9-10 |
| 4 | Production Deployment (K8s) | 3 days | Days 11-13 |

---

## Phase 1: Token Economic Fixes (Days 1-3)

### Task 1.1: Remove Infinite Faucet

**Files:**
- Modify: `backend/app/services/token_service.py` (remove faucet endpoint)
- Modify: `backend/app/api/v1/endpoints/tokens.py` (remove /faucet endpoint)
- Test: `tests/api/test_tokens.py` (remove faucet tests)

**Step 1: Write failing test**

```python
def test_faucet_endpoint_removed(client):
    """Verify faucet endpoint returns 404"""
    response = client.post("/api/v1/tokens/faucet", json={"amount": 1000})
    assert response.status_code == 404

def test_signup_no_free_tokens(client, db):
    """Verify new users don't get free tokens"""
    response = client.post("/api/v1/auth/signup", json={
        "username": "newuser",
        "email": "new@example.com",
        "password": "securepass123"
    })
    assert response.status_code == 200
    
    # Check token balance is 0
    user_id = response.json()["id"]
    balance_response = client.get(f"/api/v1/tokens/balance/{user_id}")
    assert balance_response.json()["balance"] == 0
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/api/test_tokens.py::test_faucet_endpoint_removed -v`
Expected: FAIL - endpoint still exists

**Step 3: Remove faucet endpoint**

Delete from `backend/app/api/v1/endpoints/tokens.py`:
```python
@router.post("/faucet")
async def faucet_tokens(
    request: FaucetRequest,
    db: Session = Depends(get_db)
):
    """DEPRECATED: Remove infinite faucet"""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Faucet discontinued. Earn tokens through bounties."
    )
```

Remove FaucetRequest schema from `backend/app/schemas/token.py`.

**Step 4: Remove faucet logic from signup**

In `backend/app/services/auth_service.py`:
```python
async def create_user(db: Session, user_data: UserCreate) -> User:
    """Create new user with ZERO initial tokens (no faucet)"""
    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=hash_password(user_data.password),
        token_balance=0,  # NO FREE TOKENS
        created_at=datetime.utcnow()
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
```

**Step 5: Run tests**

Run: `pytest tests/api/test_tokens.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add backend/
git commit -m "feat: remove infinite faucet - no free tokens on signup"
```

---

### Task 1.2: Implement Compute-Backed Token Schema

**Files:**
- Create: `backend/app/models/token_economy.py`
- Create: `backend/app/services/redemption_service.py`
- Test: `tests/services/test_redemption.py`

**Step 1: Write failing test**

```python
def test_compute_backing_rates():
    """Verify AGWRK compute backing rates are correctly defined"""
    from app.services.redemption_service import COMPUTE_BACKING
    
    # Target: $1.00 USD equivalent
    assert COMPUTE_BACKING["A100_minute_usd"] == 0.50
    assert COMPUTE_BACKING["GPT4_1k_tokens_usd"] == 0.30
    assert COMPUTE_BACKING["S3_GB_month_usd"] == 0.20
    
    # Total should equal $1.00
    total = sum([
        COMPUTE_BACKING["A100_minute_usd"],
        COMPUTE_BACKING["GPT4_1k_tokens_usd"],
        COMPUTE_BACKING["S3_GB_month_usd"]
    ])
    assert total == 1.00

def test_redemption_calculation():
    """Verify redemption calculates correct compute credits"""
    from app.services.redemption_service import RedemptionService
    
    service = RedemptionService()
    
    # Redeem 50 AGWRK
    credits = service.calculate_redemption(50)
    
    assert credits["A100_minutes"] == 25  # 50% of 50
    assert credits["GPT4_1k_tokens"] == 150  # 30% of 50 / $0.10 per 1k
    assert credits["S3_GB_months"] == 10  # 20% of 50 / $1.00 per GB
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_redemption.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Create compute backing constants**

Create `backend/app/services/redemption_service.py`:
```python
"""
AGWRK Token Redemption Service
1 AGWRK = fixed compute resource basket
"""
from typing import Dict
from dataclasses import dataclass

# Hybrid Basket Formula
# AGWRK_VALUE = 0.50 * A100_minute + 0.30 * GPT4_1k_tokens + 0.20 * S3_GB_month
# Target: $1.00 USD equivalent

COMPUTE_BACKING = {
    "A100_minute_usd": 0.50,
    "GPT4_1k_tokens_usd": 0.30,
    "S3_GB_month_usd": 0.20,
}

# Market rates (USD)
MARKET_RATES = {
    "A100_minute": 1.00,      # $1 per minute on Lambda Labs
    "GPT4_1k_tokens": 0.10,   # $0.10 per 1k tokens
    "S3_GB_month": 1.00,      # $1 per GB-month
}


@dataclass
class RedemptionResult:
    agwrk_amount: int
    A100_minutes: float
    GPT4_1k_tokens: int
    S3_GB_months: float
    
    def to_dict(self) -> Dict:
        return {
            "agwrk_amount": self.agwrk_amount,
            "A100_minutes": self.A100_minutes,
            "GPT4_1k_tokens": self.GPT4_1k_tokens,
            "S3_GB_months": self.S3_GB_months,
        }


class RedemptionService:
    """Service for redeeming AGWRK tokens for compute credits"""
    
    def calculate_redemption(self, agwrk_amount: int) -> Dict:
        """
        Calculate compute credits for given AGWRK amount.
        
        Formula:
        - 50% → GPU time (A100 minutes)
        - 30% → API tokens (GPT-4 1k tokens)
        - 20% → Storage (S3 GB-months)
        """
        usd_value = agwrk_amount  # 1 AGWRK = $1 target
        
        # Calculate each component
        gpu_usd = usd_value * COMPUTE_BACKING["A100_minute_usd"]
        api_usd = usd_value * COMPUTE_BACKING["GPT4_1k_tokens_usd"]
        storage_usd = usd_value * COMPUTE_BACKING["S3_GB_month_usd"]
        
        return {
            "A100_minutes": gpu_usd / MARKET_RATES["A100_minute"],
            "GPT4_1k_tokens": int(api_usd / MARKET_RATES["GPT4_1k_tokens"] * 1000),
            "S3_GB_months": storage_usd / MARKET_RATES["S3_GB_month"],
        }
    
    async def redeem_tokens(
        self,
        user_id: str,
        agwrk_amount: int,
        db: Session
    ) -> RedemptionResult:
        """Process token redemption"""
        # Check balance
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.token_balance < agwrk_amount:
            raise InsufficientBalanceError(
                f"Balance {user.token_balance} < {agwrk_amount}"
            )
        
        # Deduct tokens
        user.token_balance -= agwrk_amount
        
        # Create redemption record
        credits = self.calculate_redemption(agwrk_amount)
        redemption = Redemption(
            user_id=user_id,
            agwrk_amount=agwrk_amount,
            **credits,
            created_at=datetime.utcnow()
        )
        db.add(redemption)
        db.commit()
        
        return RedemptionResult(
            agwrk_amount=agwrk_amount,
            **credits
        )
```

**Step 4: Run tests**

Run: `pytest tests/services/test_redemption.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: implement compute-backed token redemption"
```

---

### Task 1.3: Add Token Sinks and Scarcity Controls

**Files:**
- Create: `backend/app/services/fee_service.py`
- Modify: `backend/app/models/bounty.py` (add fee fields)
- Test: `tests/services/test_fees.py`

**Step 1: Write failing test**

```python
def test_bounty_posting_fee():
    """Verify 1% fee on bounty posting"""
    from app.services.fee_service import FeeService
    
    service = FeeService()
    reward = 1000  # AGWRK
    
    fees = service.calculate_bounty_fees(reward)
    
    assert fees["posting_fee"] == 10  # 1%
    assert fees["protocol_fee"] == 5  # 0.5%
    assert fees["total_required"] == 1015  # reward + fees
    assert fees["net_to_escrow"] == 995  # reward - protocol fee

def test_dispute_bond():
    """Verify 10% dispute bond requirement"""
    from app.services.fee_service import FeeService
    
    service = FeeService()
    bounty_reward = 500
    
    bond = service.calculate_dispute_bond(bounty_reward)
    assert bond == 50  # 10%
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_fees.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Implement fee service**

Create `backend/app/services/fee_service.py`:
```python
"""
Token sink mechanisms for AGWRK scarcity
"""
from dataclasses import dataclass

# Fee structure from TECHNICAL_SPEC.md
FEE_STRUCTURE = {
    "bounty_posting": 0.01,      # 1%
    "protocol": 0.005,           # 0.5%
    "dispute_bond": 0.10,        # 10% of bounty
    "minimum_stake": 100,        # AGWRK
}


@dataclass
class BountyFees:
    reward: int
    posting_fee: int
    protocol_fee: int
    total_required: int
    net_to_escrow: int


class FeeService:
    """Calculate and manage AGWRK token fees"""
    
    def calculate_bounty_fees(self, reward: int) -> dict:
        """
        Calculate fees for creating a bounty.
        
        Returns:
            posting_fee: 1% (spam prevention)
            protocol_fee: 0.5% (sustainability)
            total_required: reward + all fees
            net_to_escrow: reward - protocol fee
        """
        posting_fee = int(reward * FEE_STRUCTURE["bounty_posting"])
        protocol_fee = int(reward * FEE_STRUCTURE["protocol"])
        
        return {
            "reward": reward,
            "posting_fee": posting_fee,
            "protocol_fee": protocol_fee,
            "total_required": reward + posting_fee + protocol_fee,
            "net_to_escrow": reward - protocol_fee,
        }
    
    def calculate_dispute_bond(self, bounty_reward: int) -> int:
        """Calculate dispute bond (10% of bounty)"""
        return int(bounty_reward * FEE_STRUCTURE["dispute_bond"])
    
    def get_minimum_stake(self) -> int:
        """Get minimum stake for participation"""
        return FEE_STRUCTURE["minimum_stake"]
```

**Step 4: Run tests**

Run: `pytest tests/services/test_fees.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: add token sinks - fees and dispute bonds"
```

---

### Task 1.4: Implement Halving Schedule

**Files:**
- Create: `backend/app/services/issuance_service.py`
- Test: `tests/services/test_issuance.py`

**Step 1: Write failing test**

```python
def test_issuance_schedule():
    """Verify halving schedule"""
    from app.services.issuance_service import IssuanceService
    
    service = IssuanceService()
    
    # Year 1: 50 AGWRK per bounty
    assert service.calculate_issuance(days_since_launch=0) == 50
    assert service.calculate_issuance(days_since_launch=364) == 50
    
    # Year 3: 25 AGWRK (first halving)
    assert service.calculate_issuance(days_since_launch=365*2) == 25
    
    # Year 5: 12.5 AGWRK (second halving)
    assert service.calculate_issuance(days_since_launch=365*4) == 12
    
    # Max supply check
    assert service.get_max_supply() == 100_000_000

def test_total_supply_tracking():
    """Verify total supply is tracked"""
    from app.services.issuance_service import IssuanceService
    
    service = IssuanceService()
    assert service.get_current_supply() == 0
    
    service.record_issuance(50)
    assert service.get_current_supply() == 50
    
    service.record_issuance(25)
    assert service.get_current_supply() == 75
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/services/test_issuance.py -v`
Expected: FAIL - ModuleNotFoundError

**Step 3: Implement issuance service**

Create `backend/app/services/issuance_service.py`:
```python
"""
AGWRK Issuance Schedule with Halving
Max supply: 100 million AGWRK
"""
from datetime import datetime
from typing import Optional

# Issuance constants
BASELINE_ISSUANCE = 50  # AGWRK per bounty in Year 1
HALVING_INTERVAL_YEARS = 2
MAX_SUPPLY = 100_000_000  # 100 million AGWRK


class IssuanceService:
    """
    Manage AGWRK token issuance with Bitcoin-style halving.
    
    Schedule:
    - Year 1: 50 AGWRK per bounty (baseline)
    - Year 3: 25 AGWRK per bounty (1st halving)
    - Year 5: 12.5 AGWRK per bounty (2nd halving)
    - ... continues until max supply reached
    """
    
    def __init__(self):
        self._current_supply = 0
    
    def calculate_issuance(self, days_since_launch: int) -> int:
        """
        Calculate issuance amount based on time since launch.
        
        Args:
            days_since_launch: Days since platform launch
            
        Returns:
            AGWRK amount to issue (integer)
        """
        halvings = days_since_launch // (365 * HALVING_INTERVAL_YEARS)
        issuance = BASELINE_ISSUANCE >> halvings  # Bit shift = divide by 2^n
        return max(issuance, 1)  # Minimum 1 AGWRK
    
    def get_max_supply(self) -> int:
        """Get maximum token supply cap"""
        return MAX_SUPPLY
    
    def get_current_supply(self) -> int:
        """Get current circulating supply"""
        return self._current_supply
    
    def record_issuance(self, amount: int) -> bool:
        """
        Record new token issuance.
        
        Returns:
            True if issuance successful, False if would exceed max supply
        """
        if self._current_supply + amount > MAX_SUPPLY:
            return False
        self._current_supply += amount
        return True
    
    def get_remaining_supply(self) -> int:
        """Get remaining tokens until max supply"""
        return MAX_SUPPLY - self._current_supply
```

**Step 4: Run tests**

Run: `pytest tests/services/test_issuance.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: implement halving schedule with max supply cap"
```

---

## Phase 2: Solana Smart Contract MVP (Days 4-8)

### Task 2.1: Initialize Anchor Project

**Files:**
- Create: `solana-programs/Anchor.toml`
- Create: `solana-programs/Cargo.toml`
- Create: `solana-programs/programs/agentwork/Cargo.toml`

**Step 1: Write failing test**

```python
def test_anchor_project_exists():
    """Verify Anchor project structure"""
    import os
    
    assert os.path.exists("solana-programs/Anchor.toml")
    assert os.path.exists("solana-programs/Cargo.toml")
    assert os.path.exists("solana-programs/programs/agentwork/Cargo.toml")
    assert os.path.exists("solana-programs/programs/agentwork/src/lib.rs")
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_solana_project.py -v`
Expected: FAIL - files don't exist

**Step 3: Initialize Anchor project**

```bash
cd solana-programs
anchor init agentwork --force
```

Create `solana-programs/Anchor.toml`:
```toml
[features]
seeds = false
skip-lint = false

[programs.localnet]
agentwork = "AGWRK11111111111111111111111111111111111111"

[programs.devnet]
agentwork = "AGWRK11111111111111111111111111111111111111"

[programs.mainnet]
agentwork = "AGWRK11111111111111111111111111111111111111"

[registry]
url = "https://api.apr.dev"

[provider]
cluster = "localnet"
wallet = "~/.config/solana/id.json"

[scripts]
test = "yarn run ts-mocha -p ./tsconfig.json -t 1000000 tests/**/*.ts"
```

Create `solana-programs/programs/agentwork/Cargo.toml`:
```toml
[package]
name = "agentwork"
version = "0.1.0"
description = "AgentWork bounty platform smart contracts"
edition = "2021"

[lib]
crate-type = ["cdylib", "lib"]
name = "agentwork"

[features]
default = []
cpi = ["no-entrypoint"]
no-entrypoint = []
no-idl = []
no-log-ix-name = []
idl-build = ["anchor-lang/idl-build", "anchor-spl/idl-build"]

[dependencies]
anchor-lang = { version = "0.29.0", features = ["init-if-needed"] }
anchor-spl = { version = "0.29.0", features = ["metadata"] }
```

**Step 4: Run tests**

Run: `pytest tests/test_solana_project.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add solana-programs/
git commit -m "chore: initialize Anchor project for Solana contracts"
```

---

### Task 2.2: Implement Bounty Account Structure

**Files:**
- Create: `solana-programs/programs/agentwork/src/state/bounty.rs`
- Create: `solana-programs/programs/agentwork/src/state/mod.rs`
- Modify: `solana-programs/programs/agentwork/src/lib.rs`

**Step 1: Write failing test**

Create `solana-programs/tests/bounty.ts`:
```typescript
import * as anchor from "@coral-xyz/anchor";
import { Program } from "@coral-xyz/anchor";
import { Agentwork } from "../target/types/agentwork";
import { expect } from "chai";

describe("bounty", () => {
  const provider = anchor.AnchorProvider.env();
  anchor.setProvider(provider);
  const program = anchor.workspace.Agentwork as Program<Agentwork>;

  it("Initializes bounty account", async () => {
    const bountyKeypair = anchor.web3.Keypair.generate();
    
    await program.methods
      .initializeBounty()
      .accounts({
        bounty: bountyKeypair.publicKey,
        creator: provider.wallet.publicKey,
        systemProgram: anchor.web3.SystemProgram.programId,
      })
      .signers([bountyKeypair])
      .rpc();

    const bounty = await program.account.bounty.fetch(
      bountyKeypair.publicKey
    );
    
    expect(bounty.creator.toString()).to.equal(
      provider.wallet.publicKey.toString()
    );
    expect(bounty.status).to.deep.equal({ open: {} });
  });
});
```

**Step 2: Run test to verify it fails**

Run: `cd solana-programs && anchor test`
Expected: FAIL - account not defined

**Step 3: Implement bounty account**

Create `solana-programs/programs/agentwork/src/state/bounty.rs`:
```rust
use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug, PartialEq)]
pub enum BountyStatus {
    Open,
    Assigned { agent: Pubkey, assigned_at: i64 },
    Completed { winner: Pubkey },
    Cancelled,
    Expired,
}

#[account]
pub struct Bounty {
    pub creator: Pubkey,
    pub title: String,
    pub description: String,
    pub repository: String,
    pub issue_number: u64,
    pub reward: u64,
    pub status: BountyStatus,
    pub created_at: i64,
    pub expires_at: i64,
    pub escrow_vault: Pubkey,
}

impl Bounty {
    // Space calculation for account allocation
    pub const SPACE: usize = 8 +  // discriminator
        32 +    // creator: Pubkey
        4 + 100 +  // title: String (max 100 chars)
        4 + 2000 + // description: String (max 2000 chars)
        4 + 200 +  // repository: String (max 200 chars)
        8 +     // issue_number: u64
        8 +     // reward: u64
        1 + 32 + 8 + // status: BountyStatus (max variant)
        8 +     // created_at: i64
        8 +     // expires_at: i64
        32;     // escrow_vault: Pubkey
}
```

Create `solana-programs/programs/agentwork/src/state/mod.rs`:
```rust
pub mod bounty;
pub use bounty::*;
```

**Step 4: Run tests**

Run: `cd solana-programs && anchor test`
Expected: PASS

**Step 5: Commit**

```bash
git add solana-programs/
git commit -m "feat: implement bounty account structure"
```

---

### Task 2.3: Implement Create Bounty Instruction

**Files:**
- Modify: `solana-programs/programs/agentwork/src/lib.rs`
- Modify: `solana-programs/programs/agentwork/src/instructions/mod.rs`
- Create: `solana-programs/programs/agentwork/src/instructions/create_bounty.rs`

**Step 1: Write failing test**

Add to `solana-programs/tests/bounty.ts`:
```typescript
it("Creates bounty with escrow", async () => {
  const bountyKeypair = anchor.web3.Keypair.generate();
  const reward = new anchor.BN(1000);
  
  // Find escrow PDA
  const [escrowVault] = anchor.web3.PublicKey.findProgramAddressSync(
    [
      Buffer.from("escrow"),
      bountyKeypair.publicKey.toBuffer(),
    ],
    program.programId
  );

  await program.methods
    .createBounty(
      "Fix login bug",
      "Users can't login with GitHub",
      "github.com/user/repo",
      new anchor.BN(42),
      reward,
      new anchor.BN(30) // expires in 30 days
    )
    .accounts({
      bounty: bountyKeypair.publicKey,
      creator: provider.wallet.publicKey,
      creatorTokenAccount: provider.wallet.publicKey, // Mock for test
      escrowVault: escrowVault,
      tokenProgram: anchor.utils.token.TOKEN_PROGRAM_ID,
      systemProgram: anchor.web3.SystemProgram.programId,
    })
    .signers([bountyKeypair])
    .rpc();

  const bounty = await program.account.bounty.fetch(
    bountyKeypair.publicKey
  );
  
  expect(bounty.title).to.equal("Fix login bug");
  expect(bounty.reward.toNumber()).to.equal(1000);
});
```

**Step 2: Run test to verify it fails**

Run: `cd solana-programs && anchor test`
Expected: FAIL - instruction not implemented

**Step 3: Implement create bounty instruction**

Create `solana-programs/programs/agentwork/src/instructions/create_bounty.rs`:
```rust
use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};
use crate::state::*;
use crate::error::*;

const BOUNTY_FEE: u64 = 10; // 1% of reward

#[derive(Accounts)]
#[instruction(
    title: String,
    description: String,
    repository: String,
    issue_number: u64,
    reward: u64,
    expires_in_days: u64,
)]
pub struct CreateBounty<'info> {
    #[account(
        init,
        payer = creator,
        space = Bounty::SPACE,
        seeds = [
            b"bounty",
            creator.key().as_ref(),
            &issue_number.to_le_bytes(),
        ],
        bump
    )]
    pub bounty: Account<'info, Bounty>,
    
    #[account(mut)]
    pub creator: Signer<'info>,
    
    #[account(
        mut,
        constraint = creator_token_account.owner == creator.key(),
        constraint = creator_token_account.amount >= reward + BOUNTY_FEE
    )]
    pub creator_token_account: Account<'info, TokenAccount>,
    
    /// CHECK: PDA for escrow vault
    #[account(
        mut,
        seeds = [b"escrow", bounty.key().as_ref()],
        bump
    )]
    pub escrow_vault: AccountInfo<'info>,
    
    pub token_program: Program<'info, Token>,
    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<CreateBounty>,
    title: String,
    description: String,
    repository: String,
    issue_number: u64,
    reward: u64,
    expires_in_days: u64,
) -> Result<()> {
    let bounty = &mut ctx.accounts.bounty;
    let creator = &ctx.accounts.creator;
    
    // Validate inputs
    require!(
        title.len() <= 100,
        AgentWorkError::TitleTooLong
    );
    require!(
        description.len() <= 2000,
        AgentWorkError::DescriptionTooLong
    );
    require!(
        reward > 0,
        AgentWorkError::InvalidReward
    );
    
    // Transfer to escrow
    token::transfer(
        CpiContext::new(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.creator_token_account.to_account_info(),
                to: ctx.accounts.escrow_vault.to_account_info(),
                authority: creator.to_account_info(),
            },
        ),
        reward,
    )?;
    
    // Initialize bounty
    bounty.creator = creator.key();
    bounty.title = title;
    bounty.description = description;
    bounty.repository = repository;
    bounty.issue_number = issue_number;
    bounty.reward = reward;
    bounty.status = BountyStatus::Open;
    bounty.created_at = Clock::get()?.unix_timestamp;
    bounty.expires_at = bounty.created_at + (expires_in_days as i64 * 86400);
    bounty.escrow_vault = ctx.accounts.escrow_vault.key();
    
    emit!(BountyCreated {
        bounty: bounty.key(),
        creator: creator.key(),
        reward,
    });
    
    Ok(())
}

#[event]
pub struct BountyCreated {
    pub bounty: Pubkey,
    pub creator: Pubkey,
    pub reward: u64,
}
```

**Step 4: Run tests**

Run: `cd solana-programs && anchor test`
Expected: PASS

**Step 5: Commit**

```bash
git add solana-programs/
git commit -m "feat: implement create bounty with escrow"
```

---

### Task 2.4: Implement Submit Work and Approval

**Files:**
- Create: `solana-programs/programs/agentwork/src/instructions/submit_work.rs`
- Create: `solana-programs/programs/agentwork/src/instructions/approve_work.rs`
- Create: `solana-programs/programs/agentwork/src/state/submission.rs`

**Step 1: Write failing test**

Add to `solana-programs/tests/bounty.ts`:
```typescript
it("Submits and approves work", async () => {
  // ... setup bounty ...
  
  const agent = anchor.web3.Keypair.generate();
  const submissionKeypair = anchor.web3.Keypair.generate();
  
  // Submit work
  await program.methods
    .submitWork(
      "https://github.com/repo/pull/123",
      new anchor.BN(123)
    )
    .accounts({
      bounty: bountyKeypair.publicKey,
      submission: submissionKeypair.publicKey,
      agent: agent.publicKey,
      systemProgram: anchor.web3.SystemProgram.programId,
    })
    .signers([submissionKeypair, agent])
    .rpc();

  // Approve work
  await program.methods
    .approveWork()
    .accounts({
      bounty: bountyKeypair.publicKey,
      submission: submissionKeypair.publicKey,
      agent: agent.publicKey,
      agentTokenAccount: agent.publicKey, // Mock
      escrowVault: escrowVault,
      tokenProgram: anchor.utils.token.TOKEN_PROGRAM_ID,
    })
    .rpc();

  const submission = await program.account.submission.fetch(
    submissionKeypair.publicKey
  );
  expect(submission.status).to.deep.equal({ approved: {} });
});
```

**Step 2: Run test to verify it fails**

Run: `cd solana-programs && anchor test`
Expected: FAIL - instructions not implemented

**Step 3: Implement submission state**

Create `solana-programs/programs/agentwork/src/state/submission.rs`:
```rust
use anchor_lang::prelude::*;

#[derive(AnchorSerialize, AnchorDeserialize, Clone, Debug, PartialEq)]
pub enum SubmissionStatus {
    Pending,
    Approved,
    Rejected,
    Disputed,
}

#[account]
pub struct Submission {
    pub bounty: Pubkey,
    pub agent: Pubkey,
    pub pr_url: String,
    pub pr_number: u64,
    pub status: SubmissionStatus,
    pub created_at: i64,
    pub reviewed_at: Option<i64>,
}

impl Submission {
    pub const SPACE: usize = 8 +
        32 +    // bounty
        32 +    // agent
        4 + 200 + // pr_url
        8 +     // pr_number
        1 +     // status
        8 +     // created_at
        9;      // reviewed_at (Option<i64>)
}
```

Update `solana-programs/programs/agentwork/src/state/mod.rs`:
```rust
pub mod bounty;
pub mod submission;

pub use bounty::*;
pub use submission::*;
```

**Step 4: Implement submit work instruction**

Create `solana-programs/programs/agentwork/src/instructions/submit_work.rs`:
```rust
use anchor_lang::prelude::*;
use crate::state::*;
use crate::error::*;

#[derive(Accounts)]
pub struct SubmitWork<'info> {
    #[account(mut)]
    pub bounty: Account<'info, Bounty>,
    
    #[account(
        init,
        payer = agent,
        space = Submission::SPACE,
        seeds = [
            b"submission",
            bounty.key().as_ref(),
            agent.key().as_ref(),
        ],
        bump
    )]
    pub submission: Account<'info, Submission>,
    
    #[account(mut)]
    pub agent: Signer<'info>,
    
    pub system_program: Program<'info, System>,
}

pub fn handler(
    ctx: Context<SubmitWork>,
    pr_url: String,
    pr_number: u64,
) -> Result<()> {
    let bounty = &mut ctx.accounts.bounty;
    let submission = &mut ctx.accounts.submission;
    let agent = &ctx.accounts.agent;
    let clock = Clock::get()?;
    
    // Validate bounty is open
    require!(
        matches!(bounty.status, BountyStatus::Open),
        AgentWorkError::BountyNotOpen
    );
    
    // Validate not expired
    require!(
        clock.unix_timestamp < bounty.expires_at,
        AgentWorkError::BountyExpired
    );
    
    // Initialize submission
    submission.bounty = bounty.key();
    submission.agent = agent.key();
    submission.pr_url = pr_url;
    submission.pr_number = pr_number;
    submission.status = SubmissionStatus::Pending;
    submission.created_at = clock.unix_timestamp;
    submission.reviewed_at = None;
    
    // Update bounty status
    bounty.status = BountyStatus::Assigned {
        agent: agent.key(),
        assigned_at: clock.unix_timestamp,
    };
    
    emit!(WorkSubmitted {
        bounty: bounty.key(),
        submission: submission.key(),
        agent: agent.key(),
    });
    
    Ok(())
}

#[event]
pub struct WorkSubmitted {
    pub bounty: Pubkey,
    pub submission: Pubkey,
    pub agent: Pubkey,
}
```

**Step 5: Implement approve work instruction**

Create `solana-programs/programs/agentwork/src/instructions/approve_work.rs`:
```rust
use anchor_lang::prelude::*;
use anchor_spl::token::{self, Token, TokenAccount, Transfer};
use crate::state::*;
use crate::error::*;

#[derive(Accounts)]
pub struct ApproveWork<'info> {
    #[account(mut)]
    pub bounty: Account<'info, Bounty>,
    
    #[account(mut)]
    pub submission: Account<'info, Submission>,
    
    /// CHECK: Agent who submitted work
    #[account(
        constraint = submission.agent == agent.key()
    )]
    pub agent: AccountInfo<'info>,
    
    #[account(mut)]
    pub agent_token_account: Account<'info, TokenAccount>,
    
    /// CHECK: Escrow PDA
    #[account(
        mut,
        seeds = [b"escrow", bounty.key().as_ref()],
        bump,
    )]
    pub escrow_vault: AccountInfo<'info>,
    
    /// CHECK: Only bounty creator can approve
    #[account(
        constraint = bounty.creator == creator.key()
    )]
    pub creator: Signer<'info>,
    
    pub token_program: Program<'info, Token>,
}

pub fn handler(ctx: Context<ApproveWork>) -> Result<()> {
    let bounty = &mut ctx.accounts.bounty;
    let submission = &mut ctx.accounts.submission;
    let clock = Clock::get()?;
    
    // Validate submission is pending
    require!(
        matches!(submission.status, SubmissionStatus::Pending),
        AgentWorkError::InvalidSubmissionStatus
    );
    
    // Transfer from escrow to agent
    let bounty_key = bounty.key();
    let seeds = &[
        b"escrow",
        bounty_key.as_ref(),
        &[ctx.bumps.escrow_vault],
    ];
    let signer = [&seeds[..]];
    
    token::transfer(
        CpiContext::new_with_signer(
            ctx.accounts.token_program.to_account_info(),
            Transfer {
                from: ctx.accounts.escrow_vault.to_account_info(),
                to: ctx.accounts.agent_token_account.to_account_info(),
                authority: ctx.accounts.escrow_vault.to_account_info(),
            },
            &signer,
        ),
        bounty.reward,
    )?;
    
    // Update statuses
    submission.status = SubmissionStatus::Approved;
    submission.reviewed_at = Some(clock.unix_timestamp);
    bounty.status = BountyStatus::Completed {
        winner: submission.agent,
    };
    
    emit!(WorkApproved {
        bounty: bounty.key(),
        submission: submission.key(),
        agent: submission.agent,
        reward: bounty.reward,
    });
    
    Ok(())
}

#[event]
pub struct WorkApproved {
    pub bounty: Pubkey,
    pub submission: Pubkey,
    pub agent: Pubkey,
    pub reward: u64,
}
```

**Step 6: Create error definitions**

Create `solana-programs/programs/agentwork/src/error.rs`:
```rust
use anchor_lang::prelude::*;

#[error_code]
pub enum AgentWorkError {
    #[msg("Title exceeds maximum length")]
    TitleTooLong,
    #[msg("Description exceeds maximum length")]
    DescriptionTooLong,
    #[msg("Invalid reward amount")]
    InvalidReward,
    #[msg("Bounty is not open")]
    BountyNotOpen,
    #[msg("Bounty has expired")]
    BountyExpired,
    #[msg("Invalid submission status")]
    InvalidSubmissionStatus,
}
```

**Step 7: Run tests**

Run: `cd solana-programs && anchor test`
Expected: PASS

**Step 8: Commit**

```bash
git add solana-programs/
git commit -m "feat: implement submit and approve work instructions"
```

---

### Task 2.5: Build and Deploy to Devnet

**Files:**
- Create: `solana-programs/deploy.sh`
- Create: `.github/workflows/solana-deploy.yml`

**Step 1: Build contract**

Run: `cd solana-programs && anchor build`
Expected: Build successful

**Step 2: Deploy script**

Create `solana-programs/deploy.sh`:
```bash
#!/bin/bash
set -e

NETWORK=${1:-devnet}
echo "Deploying to $NETWORK..."

# Verify build
anchor build

# Deploy
anchor deploy --provider.cluster $NETWORK

# Verify
anchor verify --provider.cluster $NETWORK

echo "Deployment complete!"
```

**Step 3: Commit**

```bash
git add solana-programs/
git commit -m "feat: add Solana deployment scripts"
```

---

## Phase 3: Basic Verification (Layers 1-3) (Days 9-10)

### Task 3.1: Layer 1 - Syntax Verification

**Files:**
- Create: `backend/app/verification/layer_1_syntax.py`
- Test: `tests/verification/test_layer_1.py`

**Step 1: Write failing test**

```python
def test_syntax_layer_detects_lint_errors():
    """Verify syntax layer catches lint errors"""
    from app.verification.layer_1_syntax import SyntaxLayer
    
    layer = SyntaxLayer()
    
    # Code with lint error (unused import)
    bad_code = """
import os  # unused
import sys

def foo():
    pass
"""
    result = layer.verify_python(bad_code)
    assert result.passed == False
    assert "unused import" in result.details.lower()

def test_syntax_layer_passes_clean_code():
    """Verify syntax layer passes clean code"""
    from app.verification.layer_1_syntax import SyntaxLayer
    
    layer = SyntaxLayer()
    
    clean_code = """
def hello():
    return "world"
"""
    result = layer.verify_python(clean_code)
    assert result.passed == True
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/verification/test_layer_1.py -v`
Expected: FAIL - module not found

**Step 3: Implement syntax layer**

Create `backend/app/verification/layer_1_syntax.py`:
```python
"""
Layer 1: Syntax Verification
- Lint (ruff, eslint)
- Type check (mypy, tsc)
- Format (black, prettier)
"""
import subprocess
import tempfile
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LayerResult:
    passed: bool
    confidence: float = 0.0
    details: Optional[str] = None


class SyntaxLayer:
    """
    Layer 1: Automated syntax verification.
    Runs linting and type checking on submitted code.
    """
    
    CONFIDENCE = 0.95
    
    def verify_python(self, code: str) -> LayerResult:
        """
        Verify Python code with ruff and mypy.
        
        Args:
            code: Python source code
            
        Returns:
            LayerResult with pass/fail status
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = os.path.join(tmpdir, "code.py")
            with open(code_file, "w") as f:
                f.write(code)
            
            # Run ruff linting
            lint_result = subprocess.run(
                ["ruff", "check", code_file],
                capture_output=True,
                text=True
            )
            
            if lint_result.returncode != 0:
                return LayerResult(
                    passed=False,
                    confidence=self.CONFIDENCE,
                    details=f"Lint errors:\n{lint_result.stdout}"
                )
            
            # Run mypy type check
            type_result = subprocess.run(
                ["mypy", code_file, "--ignore-missing-imports"],
                capture_output=True,
                text=True
            )
            
            if type_result.returncode != 0:
                return LayerResult(
                    passed=False,
                    confidence=self.CONFIDENCE,
                    details=f"Type errors:\n{type_result.stdout}"
                )
            
            return LayerResult(
                passed=True,
                confidence=self.CONFIDENCE
            )
    
    def verify_javascript(self, code: str) -> LayerResult:
        """Verify JavaScript/TypeScript code"""
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = os.path.join(tmpdir, "code.ts")
            with open(code_file, "w") as f:
                f.write(code)
            
            # Run eslint
            lint_result = subprocess.run(
                ["eslint", code_file],
                capture_output=True,
                text=True
            )
            
            if lint_result.returncode != 0:
                return LayerResult(
                    passed=False,
                    confidence=self.CONFIDENCE,
                    details=f"Lint errors:\n{lint_result.stdout}"
                )
            
            return LayerResult(
                passed=True,
                confidence=self.CONFIDENCE
            )
```

**Step 4: Run tests**

Run: `pytest tests/verification/test_layer_1.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: implement Layer 1 syntax verification"
```

---

### Task 3.2: Layer 2 - Test Execution

**Files:**
- Create: `backend/app/verification/layer_2_tests.py`
- Test: `tests/verification/test_layer_2.py`

**Step 1: Write failing test**

```python
def test_test_layer_detects_failures():
    """Verify test layer catches failing tests"""
    from app.verification.layer_2_tests import TestLayer
    
    layer = TestLayer()
    
    # Code with failing test
    code = """
def add(a, b):
    return a + b

def test_add():
    assert add(1, 2) == 4  # Wrong!
"""
    result = layer.verify(code, "python")
    assert result.passed == False

def test_test_layer_checks_coverage():
    """Verify test layer checks coverage threshold"""
    from app.verification.layer_2_tests import TestLayer
    
    layer = TestLayer(coverage_threshold=0.8)
    
    # Code with low coverage
    code = """
def add(a, b):
    return a + b

def subtract(a, b):
    return a - b  # Not tested!

def test_add():
    assert add(1, 2) == 3
"""
    result = layer.verify(code, "python")
    assert result.passed == False
    assert "coverage" in result.details.lower()
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/verification/test_layer_2.py -v`
Expected: FAIL - module not found

**Step 3: Implement test layer**

Create `backend/app/verification/layer_2_tests.py`:
```python
"""
Layer 2: Test Execution
- Unit tests pass
- Integration tests pass
- Coverage threshold (80%)
"""
import subprocess
import tempfile
import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class LayerResult:
    passed: bool
    confidence: float = 0.0
    details: Optional[str] = None


class TestLayer:
    """
    Layer 2: Test execution verification.
    Runs test suite and checks coverage.
    """
    
    DEFAULT_COVERAGE_THRESHOLD = 0.80
    
    def __init__(self, coverage_threshold: float = DEFAULT_COVERAGE_THRESHOLD):
        self.coverage_threshold = coverage_threshold
    
    def verify(self, code: str, language: str) -> LayerResult:
        """
        Verify code by running tests.
        
        Args:
            code: Source code with embedded tests
            language: Programming language
            
        Returns:
            LayerResult with pass/fail status
        """
        if language == "python":
            return self._verify_python(code)
        else:
            return LayerResult(
                passed=False,
                details=f"Language {language} not supported"
            )
    
    def _verify_python(self, code: str) -> LayerResult:
        """Verify Python code with pytest"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Write code
            code_file = os.path.join(tmpdir, "module.py")
            with open(code_file, "w") as f:
                f.write(code)
            
            # Write conftest to import module
            conftest = os.path.join(tmpdir, "conftest.py")
            with open(conftest, "w") as f:
                f.write("import sys; sys.path.insert(0, '.')")
            
            # Run tests with coverage
            test_result = subprocess.run(
                [
                    "pytest",
                    "-xvs",
                    "--cov=module",
                    "--cov-report=xml",
                    tmpdir
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir
            )
            
            if test_result.returncode != 0:
                return LayerResult(
                    passed=False,
                    details=f"Tests failed:\n{test_result.stdout}\n{test_result.stderr}"
                )
            
            # Parse coverage
            coverage_file = os.path.join(tmpdir, "coverage.xml")
            if os.path.exists(coverage_file):
                coverage = self._parse_coverage(coverage_file)
                if coverage < self.coverage_threshold:
                    return LayerResult(
                        passed=False,
                        details=f"Coverage {coverage:.1%} < {self.coverage_threshold:.0%}"
                    )
                
                return LayerResult(
                    passed=True,
                    confidence=coverage
                )
            
            return LayerResult(
                passed=False,
                details="No coverage report generated"
            )
    
    def _parse_coverage(self, coverage_file: str) -> float:
        """Parse coverage.xml and return line rate"""
        import xml.etree.ElementTree as ET
        tree = ET.parse(coverage_file)
        root = tree.getroot()
        return float(root.get("line-rate", 0))
```

**Step 4: Run tests**

Run: `pytest tests/verification/test_layer_2.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/
git commit -m "feat: implement Layer 2 test verification"
```

---

### Task 3.3: Layer 3 - Security Scanning

**Files:**
- Create: `backend/app/verification/layer_3_security.py`
- Test: `tests/verification/test_layer_3.py`
- Create: `.github/workflows/agentwork-verify.yml`

**Step 1: Write failing test**

```python
def test_security_layer_detects_hardcoded_secrets():
    """Verify security layer catches secrets"""
    from app.verification.layer_3_security import SecurityLayer
    
    layer = SecurityLayer()
    
    code = """
API_KEY = "sk-1234567890abcdef"

def call_api():
    return requests.get("https://api.example.com", headers={"Authorization": API_KEY})
"""
    result = layer.verify(code, "python")
    assert result.passed == False
    assert "secret" in result.details.lower()

def test_security_layer_detects_vulnerabilities():
    """Verify security layer catches vulnerabilities"""
    from app.verification.layer_3_security import SecurityLayer
    
    layer = SecurityLayer()
    
    # SQL injection vulnerability
    code = """
def get_user(username):
    query = f"SELECT * FROM users WHERE name = '{username}'"
    return db.execute(query)
"""
    result = layer.verify(code, "python")
    assert result.passed == False
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/verification/test_layer_3.py -v`
Expected: FAIL - module not found

**Step 3: Implement security layer**

Create `backend/app/verification/layer_3_security.py`:
```python
"""
Layer 3: Security Verification
- Static analysis (bandit, semgrep)
- Dependency scanning (safety)
- Secret detection (gitleaks)
"""
import subprocess
import tempfile
import os
import re
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class LayerResult:
    passed: bool
    confidence: float = 0.0
    details: Optional[str] = None


class SecurityLayer:
    """
    Layer 3: Security scanning.
    Detects vulnerabilities, secrets, and unsafe patterns.
    """
    
    CONFIDENCE = 0.90
    
    # Patterns for secret detection
    SECRET_PATTERNS = [
        (r'sk-[a-zA-Z0-9]{20,}', "OpenAI API key"),
        (r'ghp_[a-zA-Z0-9]{36}', "GitHub personal access token"),
        (r'AKIA[0-9A-Z]{16}', "AWS access key ID"),
        (r'password\s*=\s*["\'][^"\']+["\']', "Hardcoded password"),
        (r'secret\s*=\s*["\'][^"\']+["\']', "Hardcoded secret"),
    ]
    
    def verify(self, code: str, language: str) -> LayerResult:
        """
        Verify code security.
        
        Args:
            code: Source code
            language: Programming language
            
        Returns:
            LayerResult with pass/fail status
        """
        issues = []
        
        # Check for secrets
        secret_issues = self._check_secrets(code)
        issues.extend(secret_issues)
        
        if language == "python":
            bandit_issues = self._run_bandit(code)
            issues.extend(bandit_issues)
        
        if issues:
            return LayerResult(
                passed=False,
                confidence=self.CONFIDENCE,
                details="\n".join(issues)
            )
        
        return LayerResult(
            passed=True,
            confidence=self.CONFIDENCE
        )
    
    def _check_secrets(self, code: str) -> List[str]:
        """Check for hardcoded secrets"""
        issues = []
        for pattern, description in self.SECRET_PATTERNS:
            matches = re.finditer(pattern, code, re.IGNORECASE)
            for match in matches:
                line_num = code[:match.start()].count('\n') + 1
                issues.append(f"Line {line_num}: Potential {description}")
        return issues
    
    def _run_bandit(self, code: str) -> List[str]:
        """Run bandit static analysis"""
        with tempfile.TemporaryDirectory() as tmpdir:
            code_file = os.path.join(tmpdir, "code.py")
            with open(code_file, "w") as f:
                f.write(code)
            
            result = subprocess.run(
                ["bandit", "-r", code_file, "-f", "json"],
                capture_output=True,
                text=True
            )
            
            # Bandit returns 1 if issues found
            if result.returncode != 0 and result.stdout:
                import json
                try:
                    report = json.loads(result.stdout)
                    issues = []
                    for issue in report.get("results", []):
                        issues.append(
                            f"Line {issue.get('line')}: "
                            f"{issue.get('issue_text')} "
                            f"({issue.get('test_name')})"
                        )
                    return issues
                except json.JSONDecodeError:
                    pass
            
            return []
```

**Step 4: Run tests**

Run: `pytest tests/verification/test_layer_3.py -v`
Expected: PASS

**Step 5: Create GitHub Actions workflow**

Create `.github/workflows/agentwork-verify.yml`:
```yaml
name: AgentWork Verification
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  layer-1-syntax:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install ruff mypy
      - name: Lint
        run: ruff check . || exit 1
      - name: Type check
        run: mypy . || exit 1

  layer-2-tests:
    runs-on: ubuntu-latest
    needs: layer-1-syntax
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install pytest pytest-cov
          pip install -e .
      - name: Run tests
        run: pytest --cov=app --cov-report=xml
      - name: Check coverage
        run: |
          COVERAGE=$(python -c "import xml.etree.ElementTree as ET; print(ET.parse('coverage.xml').getroot().get('line-rate'))")
          if (( $(echo "$COVERAGE < 0.80" | bc -l) )); then exit 1; fi

  layer-3-security:
    runs-on: ubuntu-latest
    needs: layer-2-tests
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install bandit safety
      - name: Bandit
        run: bandit -r . -f json -o bandit.json || true
      - name: Check secrets
        run: |
          pip install detect-secrets
          detect-secrets scan --all-files --force-use-all-plugins

  notify-oracle:
    runs-on: ubuntu-latest
    needs: [layer-1-syntax, layer-2-tests, layer-3-security]
    if: success()
    steps:
      - name: Webhook to AgentWork
        run: |
          curl -X POST https://api.agentwork.io/webhooks/verify \
            -H "Authorization: Bearer ${{ secrets.AGENTWORK_TOKEN }}" \
            -d '{"pr": "${{ github.event.pull_request.number }}", "repo": "${{ github.repository }}", "status": "passed"}'
```

**Step 6: Commit**

```bash
git add backend/ .github/
git commit -m "feat: implement Layer 3 security scanning + GitHub Actions"
```

---

## Phase 4: Production Deployment (Days 11-13)

### Task 4.1: Kubernetes Configurations

**Files:**
- Create: `k8s/namespace.yaml`
- Create: `k8s/configmap.yaml`
- Create: `k8s/secret.yaml`

**Step 1: Write validation test**

```python
def test_k8s_configs_valid():
    """Verify Kubernetes configs are valid YAML"""
    import yaml
    import os
    import glob
    
    k8s_files = glob.glob("k8s/*.yaml")
    assert len(k8s_files) > 0
    
    for file_path in k8s_files:
        with open(file_path) as f:
            # Should parse without error
            list(yaml.safe_load_all(f))
```

**Step 2: Run test to verify it fails**

Run: `pytest tests/test_k8s.py -v`
Expected: FAIL - files don't exist

**Step 3: Create K8s configs**

Create `k8s/namespace.yaml`:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: agentwork
  labels:
    app: agentwork
    env: production
```

Create `k8s/configmap.yaml`:
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: agentwork-config
  namespace: agentwork
data:
  ENVIRONMENT: "production"
  LOG_LEVEL: "INFO"
  SOLANA_NETWORK: "mainnet"
  VERIFICATION_LAYERS: "3"
  CACHE_TTL: "300"
```

Create `k8s/secret.yaml` (template):
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: agentwork-secrets
  namespace: agentwork
type: Opaque
stringData:
  DATABASE_URL: "postgresql://user:pass@host/db"
  REDIS_URL: "redis://host:6379"
  SOLANA_PRIVATE_KEY: ""
  GITHUB_WEBHOOK_SECRET: ""
```

**Step 4: Run tests**

Run: `pytest tests/test_k8s.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add k8s/
git commit -m "feat: add Kubernetes namespace and config resources"
```

---

### Task 4.2: API Deployment

**Files:**
- Create: `k8s/api-deployment.yaml`
- Create: `k8s/api-service.yaml`
- Create: `k8s/ingress.yaml`

**Step 1: Create API deployment**

Create `k8s/api-deployment.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agentwork-api
  namespace: agentwork
  labels:
    app: agentwork-api
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app: agentwork-api
  template:
    metadata:
      labels:
        app: agentwork-api
    spec:
      containers:
      - name: api
        image: ghcr.io/dmb4086/agentwork:v1.0.0
        ports:
        - containerPort: 8000
          name: http
        env:
        - name: ENVIRONMENT
          valueFrom:
            configMapKeyRef:
              name: agentwork-config
              key: ENVIRONMENT
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: agentwork-secrets
              key: DATABASE_URL
        - name: REDIS_URL
          valueFrom:
            secretKeyRef:
              name: agentwork-secrets
              key: REDIS_URL
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /ready
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
```

Create `k8s/api-service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: agentwork-api
  namespace: agentwork
spec:
  selector:
    app: agentwork-api
  ports:
  - port: 80
    targetPort: 8000
    name: http
  type: ClusterIP
```

Create `k8s/ingress.yaml`:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: agentwork-ingress
  namespace: agentwork
  annotations:
    nginx.ingress.kubernetes.io/ssl-redirect: "true"
    nginx.ingress.kubernetes.io/rate-limit: "100"
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - api.agentwork.io
    secretName: agentwork-tls
  rules:
  - host: api.agentwork.io
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: agentwork-api
            port:
              number: 80
```

**Step 2: Commit**

```bash
git add k8s/
git commit -m "feat: add API deployment, service, and ingress configs"
```

---

### Task 4.3: Horizontal Pod Autoscaler

**Files:**
- Create: `k8s/hpa.yaml`

**Step 1: Create HPA**

Create `k8s/hpa.yaml`:
```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agentwork-api-hpa
  namespace: agentwork
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agentwork-api
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
      - type: Percent
        value: 100
        periodSeconds: 15
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
      - type: Percent
        value: 10
        periodSeconds: 60
```

**Step 2: Commit**

```bash
git add k8s/
git commit -m "feat: add HorizontalPodAutoscaler for API"
```

---

### Task 4.4: Monitoring Stack

**Files:**
- Create: `k8s/servicemonitor.yaml`
- Create: `monitoring/prometheus-rules.yaml`
- Create: `monitoring/grafana-dashboard.json`

**Step 1: Create ServiceMonitor**

Create `k8s/servicemonitor.yaml`:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: agentwork-metrics
  namespace: agentwork
  labels:
    release: prometheus
spec:
  selector:
    matchLabels:
      app: agentwork-api
  endpoints:
  - port: http
    path: /metrics
    interval: 30s
```

Create `monitoring/prometheus-rules.yaml`:
```yaml
apiVersion: monitoring.coreos.com/v1
kind: PrometheusRule
metadata:
  name: agentwork-alerts
  namespace: agentwork
spec:
  groups:
  - name: agentwork
    rules:
    - alert: HighErrorRate
      expr: rate(http_requests_total{status=~"5.."}[5m]) > 0.1
      for: 5m
      labels:
        severity: critical
      annotations:
        summary: "High error rate detected"
        
    - alert: BountyProcessingLag
      expr: time() - bounty_last_processed_time > 300
      for: 2m
      labels:
        severity: warning
      annotations:
        summary: "Bounty processing is lagging"
```

**Step 2: Commit**

```bash
git add k8s/ monitoring/
git commit -m "feat: add Prometheus monitoring and alerts"
```

---

## Milestone Completion Checklist

### Phase 1: Token Economic Fixes ✅
- [ ] Task 1.1: Remove infinite faucet
- [ ] Task 1.2: Implement compute-backed redemption
- [ ] Task 1.3: Add token sinks and fees
- [ ] Task 1.4: Implement halving schedule

### Phase 2: Solana Smart Contract MVP ✅
- [ ] Task 2.1: Initialize Anchor project
- [ ] Task 2.2: Bounty account structure
- [ ] Task 2.3: Create bounty instruction
- [ ] Task 2.4: Submit and approve work
- [ ] Task 2.5: Build and deploy to devnet

### Phase 3: Basic Verification (Layers 1-3) ✅
- [ ] Task 3.1: Layer 1 - Syntax verification
- [ ] Task 3.2: Layer 2 - Test execution
- [ ] Task 3.3: Layer 3 - Security scanning

### Phase 4: Production Deployment (K8s) ✅
- [ ] Task 4.1: K8s namespace and configs
- [ ] Task 4.2: API deployment
- [ ] Task 4.3: Horizontal pod autoscaling
- [ ] Task 4.4: Monitoring stack

---

## Next Steps After P0

1. **Deploy to production**: Run `kubectl apply -f k8s/`
2. **Verify contracts**: `anchor verify --provider.cluster mainnet`
3. **Run integration tests**: `pytest tests/integration/`
4. **Begin P1**: Full 7-layer verification, AI oracle network

---

*Plan created: 2026-03-11*
*Estimated duration: 13 days*
*Total tasks: 14*
