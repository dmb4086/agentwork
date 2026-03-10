"""
Solana Bridge Module: Connects PostgreSQL token balances with Solana blockchain.

This module provides:
- RPC client for Solana blockchain interaction
- Transaction handling for token transfers
- Event listening for blockchain events
- PostgreSQL synchronization for token balances

Architecture:
    PostgreSQL (token balances) <-> Solana Bridge <-> Solana Blockchain
                              (sync, validate, reconcile)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum, auto
from typing import Any, Callable, Optional
from uuid import UUID

import aiohttp
from solders.hash import Hash
from solders.keypair import Keypair
from solders.message import MessageV0
from solders.pubkey import Pubkey
from solders.rpc.responses import GetSignatureStatusesResp, SendTransactionResp
from solders.signature import Signature
from solders.system_program import CreateAccountParams, create_account
from solders.transaction import VersionedTransaction

# Database imports (PostgreSQL)
import asyncpg
from asyncpg import Pool, Record

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BridgeError(Exception):
    """Base exception for bridge operations."""
    pass


class InsufficientBalanceError(BridgeError):
    """Raised when account has insufficient balance for operation."""
    pass


class TransactionFailedError(BridgeError):
    """Raised when a blockchain transaction fails."""
    pass


class SyncError(BridgeError):
    """Raised when database-blockchain synchronization fails."""
    pass


class EventType(Enum):
    """Types of blockchain events to listen for."""
    BOUNTY_CREATED = auto()
    WORK_SUBMITTED = auto()
    WORK_APPROVED = auto()
    DISPUTE_RAISED = auto()
    TRANSFER = auto()
    STAKE_DEPOSITED = auto()
    STAKE_WITHDRAWN = auto()


@dataclass
class TokenBalance:
    """Represents a token balance in PostgreSQL and blockchain."""
    user_id: UUID
    wallet_address: str
    balance: Decimal
    staked_amount: Decimal = Decimal("0")
    pending_rewards: Decimal = Decimal("0")
    last_synced_at: Optional[str] = None
    chain_version: int = 0  # Optimistic locking
    
    def available_balance(self) -> Decimal:
        """Return balance available for transfer (excluding staked)."""
        return self.balance - self.staked_amount
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": str(self.user_id),
            "wallet_address": self.wallet_address,
            "balance": str(self.balance),
            "staked_amount": str(self.staked_amount),
            "pending_rewards": str(self.pending_rewards),
            "last_synced_at": self.last_synced_at,
            "chain_version": self.chain_version,
        }


@dataclass
class BlockchainEvent:
    """Represents a blockchain event."""
    event_type: EventType
    signature: str
    slot: int
    timestamp: Optional[int] = None
    data: dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type.name,
            "signature": self.signature,
            "slot": self.slot,
            "timestamp": self.timestamp,
            "data": self.data,
        }


@dataclass
class TransactionResult:
    """Result of a blockchain transaction."""
    success: bool
    signature: Optional[str] = None
    error: Optional[str] = None
    slot: Optional[int] = None
    confirmations: int = 0
    
    def raise_for_error(self) -> None:
        """Raise exception if transaction failed."""
        if not self.success:
            raise TransactionFailedError(self.error or "Transaction failed")


class SolanaRPCClient:
    """
    Async Solana RPC client with connection pooling and retry logic.
    
    Supports:
    - HTTP/HTTPS RPC endpoints
    - Automatic retry with exponential backoff
    - Request batching for efficiency
    - Commitment level configuration
    """
    
    COMMITMENT_LEVELS = {
        "processed": "processed",
        "confirmed": "confirmed",
        "finalized": "finalized",
    }
    
    def __init__(
        self,
        endpoint: str,
        commitment: str = "confirmed",
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.endpoint = endpoint
        self.commitment = commitment
        self.timeout = timeout
        self.max_retries = max_retries
        self._session: Optional[aiohttp.ClientSession] = None
        self._request_id = 0
        
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout),
                headers={"Content-Type": "application/json"},
            )
        return self._session
    
    def _get_request_id(self) -> int:
        """Generate unique request ID."""
        self._request_id += 1
        return self._request_id
    
    async def _rpc_call(
        self,
        method: str,
        params: Optional[list[Any]] = None,
    ) -> dict[str, Any]:
        """
        Make RPC call with retry logic.
        
        Args:
            method: RPC method name
            params: RPC parameters
            
        Returns:
            JSON-RPC response
            
        Raises:
            BridgeError: If all retries exhausted
        """
        session = await self._get_session()
        request = {
            "jsonrpc": "2.0",
            "id": self._get_request_id(),
            "method": method,
            "params": params or [],
        }
        
        last_error = None
        for attempt in range(self.max_retries):
            try:
                async with session.post(
                    self.endpoint,
                    json=request,
                ) as response:
                    if response.status != 200:
                        raise BridgeError(
                            f"HTTP {response.status}: {await response.text()}"
                        )
                    result = await response.json()
                    if "error" in result:
                        raise BridgeError(f"RPC Error: {result['error']}")
                    return result["result"]
            except asyncio.TimeoutError as e:
                last_error = e
                wait = 2 ** attempt  # Exponential backoff
                logger.warning(f"RPC timeout, retrying in {wait}s...")
                await asyncio.sleep(wait)
            except Exception as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(f"RPC error: {e}, retrying in {wait}s...")
                await asyncio.sleep(wait)
        
        raise BridgeError(f"RPC failed after {self.max_retries} attempts: {last_error}")
    
    async def get_balance(self, address: str) -> int:
        """Get SOL balance for address (in lamports)."""
        result = await self._rpc_call("getBalance", [address])
        return result["value"]
    
    async def get_token_balance(
        self,
        address: str,
        mint: str,
    ) -> dict[str, Any]:
        """Get SPL token balance for address."""
        params = [
            address,
            {"mint": mint, "commitment": self.commitment},
        ]
        return await self._rpc_call("getTokenAccountsByOwner", params)
    
    async def get_account_info(self, address: str) -> Optional[dict[str, Any]]:
        """Get account information."""
        params = [address, {"commitment": self.commitment}]
        result = await self._rpc_call("getAccountInfo", params)
        return result.get("value")
    
    async def get_latest_blockhash(self) -> str:
        """Get latest blockhash for transaction."""
        params = [{"commitment": self.commitment}]
        result = await self._rpc_call("getLatestBlockhash", params)
        return result["value"]["blockhash"]
    
    async def send_transaction(
        self,
        transaction: str,
    ) -> str:
        """
        Send signed transaction to blockchain.
        
        Args:
            transaction: Base64-encoded signed transaction
            
        Returns:
            Transaction signature
        """
        params = [
            transaction,
            {
                "encoding": "base64",
                "preflightCommitment": self.commitment,
                "maxRetries": 3,
            },
        ]
        result = await self._rpc_call("sendTransaction", params)
        return result
    
    async def confirm_transaction(
        self,
        signature: str,
        timeout: float = 60.0,
    ) -> TransactionResult:
        """
        Wait for transaction confirmation.
        
        Args:
            signature: Transaction signature
            timeout: Maximum wait time in seconds
            
        Returns:
            TransactionResult with status
        """
        start = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start < timeout:
            params = [
                [signature],
                {"commitment": self.commitment},
            ]
            result = await self._rpc_call("getSignatureStatuses", params)
            
            if result["value"] and len(result["value"]) > 0:
                status = result["value"][0]
                
                if status is None:
                    await asyncio.sleep(0.5)
                    continue
                
                if status.get("err"):
                    return TransactionResult(
                        success=False,
                        signature=signature,
                        error=str(status["err"]),
                    )
                
                if status.get("confirmationStatus") in ["confirmed", "finalized"]:
                    return TransactionResult(
                        success=True,
                        signature=signature,
                        slot=status.get("slot"),
                        confirmations=status.get("confirmations") or 0,
                    )
            
            await asyncio.sleep(0.5)
        
        return TransactionResult(
            success=False,
            signature=signature,
            error="Confirmation timeout",
        )
    
    async def get_program_accounts(
        self,
        program_id: str,
        filters: Optional[list[dict]] = None,
    ) -> list[dict[str, Any]]:
        """Get accounts owned by a program."""
        params = [
            program_id,
            {
                "commitment": self.commitment,
                "filters": filters or [],
                "encoding": "base64",
            },
        ]
        return await self._rpc_call("getProgramAccounts", params)
    
    async def close(self) -> None:
        """Close RPC client connection."""
        if self._session and not self._session.closed:
            await self._session.close()


class TokenBridge:
    """
    Bridge between PostgreSQL token balances and Solana blockchain.
    
    Handles:
    - Bidirectional sync between DB and blockchain
    - Transaction creation and signing
    - Balance reconciliation
    - Event processing
    """
    
    def __init__(
        self,
        rpc_client: SolanaRPCClient,
        db_pool: Pool,
        program_id: str,
        mint_address: str,
        treasury_wallet: str,
        decimals: int = 6,
    ):
        self.rpc = rpc_client
        self.db = db_pool
        self.program_id = Pubkey.from_string(program_id)
        self.mint_address = Pubkey.from_string(mint_address)
        self.treasury_wallet = Pubkey.from_string(treasury_wallet)
        self.decimals = decimals
        self._event_handlers: dict[EventType, list[Callable]] = {}
        self._running = False
        
    def on_event(
        self,
        event_type: EventType,
        handler: Callable[[BlockchainEvent], Any],
    ) -> None:
        """Register event handler."""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def _emit_event(self, event: BlockchainEvent) -> None:
        """Emit event to registered handlers."""
        handlers = self._event_handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error(f"Event handler error: {e}")
    
    # ========== Database Operations ==========
    
    async def get_balance_from_db(
        self,
        user_id: UUID,
    ) -> Optional[TokenBalance]:
        """Get token balance from PostgreSQL."""
        query = """
            SELECT 
                user_id,
                wallet_address,
                balance,
                staked_amount,
                pending_rewards,
                last_synced_at,
                chain_version
            FROM token_balances
            WHERE user_id = $1
        """
        row = await self.db.fetchrow(query, user_id)
        
        if not row:
            return None
        
        return TokenBalance(
            user_id=row["user_id"],
            wallet_address=row["wallet_address"],
            balance=Decimal(str(row["balance"])),
            staked_amount=Decimal(str(row["staked_amount"])),
            pending_rewards=Decimal(str(row["pending_rewards"])),
            last_synced_at=row["last_synced_at"],
            chain_version=row["chain_version"],
        )
    
    async def update_balance_in_db(
        self,
        balance: TokenBalance,
    ) -> bool:
        """
        Update token balance in PostgreSQL with optimistic locking.
        
        Args:
            balance: Updated balance with expected version
            
        Returns:
            True if update succeeded, False if version conflict
        """
        query = """
            UPDATE token_balances
            SET 
                balance = $1,
                staked_amount = $2,
                pending_rewards = $3,
                last_synced_at = NOW(),
                chain_version = chain_version + 1
            WHERE user_id = $4 AND chain_version = $5
            RETURNING chain_version
        """
        row = await self.db.fetchrow(
            query,
            balance.balance,
            balance.staked_amount,
            balance.pending_rewards,
            balance.user_id,
            balance.chain_version,
        )
        
        if row:
            balance.chain_version = row["chain_version"]
            return True
        return False
    
    async def create_balance_record(
        self,
        user_id: UUID,
        wallet_address: str,
    ) -> TokenBalance:
        """Create new token balance record in DB."""
        query = """
            INSERT INTO token_balances 
                (user_id, wallet_address, balance, staked_amount, pending_rewards, chain_version)
            VALUES ($1, $2, 0, 0, 0, 0)
            ON CONFLICT (user_id) DO NOTHING
            RETURNING *
        """
        await self.db.execute(query, user_id, wallet_address)
        
        balance = await self.get_balance_from_db(user_id)
        if not balance:
            raise SyncError(f"Failed to create balance record for {user_id}")
        return balance
    
    async def record_transaction(
        self,
        user_id: UUID,
        tx_type: str,
        amount: Decimal,
        signature: str,
        status: str = "pending",
    ) -> None:
        """Record transaction in database for audit trail."""
        query = """
            INSERT INTO token_transactions 
                (user_id, tx_type, amount, signature, status, created_at)
            VALUES ($1, $2, $3, $4, $5, NOW())
        """
        await self.db.execute(query, user_id, tx_type, amount, signature, status)
    
    # ========== Blockchain Operations ==========
    
    async def get_chain_balance(self, wallet_address: str) -> Decimal:
        """
        Get token balance directly from blockchain.
        
        Args:
            wallet_address: Wallet address to query
            
        Returns:
            Token balance as Decimal
        """
        try:
            result = await self.rpc.get_token_balance(
                wallet_address,
                str(self.mint_address),
            )
            
            if not result.get("value"):
                return Decimal("0")
            
            accounts = result["value"]
            total = Decimal("0")
            
            for account in accounts:
                parsed = account.get("account", {}).get("data", {}).get("parsed", {})
                info = parsed.get("info", {})
                amount = info.get("tokenAmount", {}).get("uiAmount", 0)
                total += Decimal(str(amount))
            
            return total
        except Exception as e:
            logger.error(f"Failed to get chain balance: {e}")
            raise BridgeError(f"Chain balance query failed: {e}")
    
    async def sync_balance(
        self,
        user_id: UUID,
    ) -> TokenBalance:
        """
        Synchronize PostgreSQL balance with blockchain.
        
        Resolves conflicts by treating blockchain as source of truth.
        
        Args:
            user_id: User to sync
            
        Returns:
            Updated TokenBalance
        """
        # Get DB state
        db_balance = await self.get_balance_from_db(user_id)
        if not db_balance:
            raise SyncError(f"No balance record for user {user_id}")
        
        # Get chain state
        chain_balance = await self.get_chain_balance(db_balance.wallet_address)
        
        # Reconcile if different
        if chain_balance != db_balance.balance:
            logger.info(
                f"Balance mismatch for {user_id}: "
                f"DB={db_balance.balance}, Chain={chain_balance}"
            )
            db_balance.balance = chain_balance
            db_balance.last_synced_at = str(asyncio.get_event_loop().time())
            
            # Update with retry for optimistic locking
            for _ in range(3):
                if await self.update_balance_in_db(db_balance):
                    break
                # Refresh and retry
                db_balance = await self.get_balance_from_db(user_id)
                if db_balance:
                    db_balance.balance = chain_balance
            else:
                raise SyncError(f"Failed to sync balance for {user_id}")
        
        return db_balance
    
    async def mint_tokens(
        self,
        recipient_wallet: str,
        amount: Decimal,
        authority_keypair: Keypair,
    ) -> TransactionResult:
        """
        Mint new tokens to recipient (treasury operation).
        
        Args:
            recipient_wallet: Target wallet address
            amount: Amount to mint
            authority_keypair: Mint authority keypair
            
        Returns:
            TransactionResult
        """
        # Build mint instruction (placeholder - actual impl needs SPL token program)
        # This would use spl_token.instruction.mint_to in full implementation
        
        recipient = Pubkey.from_string(recipient_wallet)
        
        # Get recent blockhash
        blockhash = await self.rpc.get_latest_blockhash()
        blockhash_obj = Hash.from_string(blockhash)
        
        # Build transaction message
        # Note: Full implementation would use SPL token instructions
        message = MessageV0.try_compile(
            payer=authority_keypair.pubkey(),
            instructions=[],  # Would include mint instruction
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash_obj,
        )
        
        # Sign transaction
        tx = VersionedTransaction(message, [authority_keypair])
        serialized = base64.b64encode(bytes(tx)).decode()
        
        # Send and confirm
        signature = await self.rpc.send_transaction(serialized)
        result = await self.rpc.confirm_transaction(signature)
        
        if result.success:
            logger.info(f"Minted {amount} tokens to {recipient_wallet}: {signature}")
        
        return result
    
    async def transfer_tokens(
        self,
        from_wallet: str,
        to_wallet: str,
        amount: Decimal,
        from_keypair: Keypair,
    ) -> TransactionResult:
        """
        Transfer tokens between wallets.
        
        Args:
            from_wallet: Sender wallet address
            to_wallet: Recipient wallet address
            amount: Amount to transfer
            from_keypair: Sender's keypair
            
        Returns:
            TransactionResult
        """
        # In full implementation, this would:
        # 1. Get or create associated token accounts
        # 2. Build SPL transfer instruction
        # 3. Sign and send transaction
        
        blockhash = await self.rpc.get_latest_blockhash()
        blockhash_obj = Hash.from_string(blockhash)
        
        # Build transfer message (placeholder)
        message = MessageV0.try_compile(
            payer=from_keypair.pubkey(),
            instructions=[],  # Would include transfer instruction
            address_lookup_table_accounts=[],
            recent_blockhash=blockhash_obj,
        )
        
        tx = VersionedTransaction(message, [from_keypair])
        serialized = base64.b64encode(bytes(tx)).decode()
        
        signature = await self.rpc.send_transaction(serialized)
        result = await self.rpc.confirm_transaction(signature)
        
        if result.success:
            logger.info(
                f"Transferred {amount} from {from_wallet} to {to_wallet}: {signature}"
            )
        
        return result
    
    async def stake_tokens(
        self,
        user_id: UUID,
        amount: Decimal,
        user_keypair: Keypair,
    ) -> TransactionResult:
        """
        Stake tokens for user.
        
        Updates both blockchain and PostgreSQL atomically.
        
        Args:
            user_id: User ID
            amount: Amount to stake
            user_keypair: User's keypair
            
        Returns:
            TransactionResult
        """
        balance = await self.get_balance_from_db(user_id)
        if not balance:
            raise BridgeError(f"No balance record for {user_id}")
        
        if balance.available_balance() < amount:
            raise InsufficientBalanceError(
                f"Insufficient balance: {balance.available_balance()} < {amount}"
            )
        
        # Update DB first (optimistic)
        balance.staked_amount += amount
        
        try:
            # Execute on-chain stake (placeholder)
            result = await self.transfer_tokens(
                balance.wallet_address,
                str(self.treasury_wallet),
                amount,
                user_keypair,
            )
            
            if result.success:
                await self.update_balance_in_db(balance)
                await self.record_transaction(
                    user_id,
                    "stake",
                    amount,
                    result.signature or "",
                    "confirmed",
                )
            else:
                # Rollback DB change
                balance.staked_amount -= amount
                await self.update_balance_in_db(balance)
            
            return result
        except Exception as e:
            # Rollback
            balance.staked_amount -= amount
            await self.update_balance_in_db(balance)
            raise
    
    # ========== Event Listening ==========
    
    async def start_event_listener(
        self,
        poll_interval: float = 2.0,
    ) -> None:
        """
        Start listening for blockchain events.
        
        Polls for program account changes and emits events.
        
        Args:
            poll_interval: Seconds between polls
        """
        self._running = True
        last_slot = await self.rpc._rpc_call("getSlot", [])
        
        logger.info(f"Starting event listener from slot {last_slot}")
        
        while self._running:
            try:
                # Get signatures for program
                signatures = await self.rpc._rpc_call(
                    "getSignaturesForAddress",
                    [
                        str(self.program_id),
                        {"commitment": self.rpc.commitment},
                    ],
                )
                
                for sig_info in signatures:
                    slot = sig_info.get("slot", 0)
                    if slot <= last_slot:
                        continue
                    
                    signature = sig_info["signature"]
                    
                    # Get transaction details
                    tx_details = await self.rpc._rpc_call(
                        "getTransaction",
                        [
                            signature,
                            {"commitment": self.rpc.commitment, "encoding": "json"},
                        ],
                    )
                    
                    if tx_details:
                        await self._process_transaction_event(
                            signature,
                            slot,
                            tx_details,
                        )
                
                last_slot = max(
                    last_slot,
                    max((s.get("slot", 0) for s in signatures), default=last_slot),
                )
                
                await asyncio.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"Event listener error: {e}")
                await asyncio.sleep(poll_interval)
    
    async def _process_transaction_event(
        self,
        signature: str,
        slot: int,
        tx_details: dict[str, Any],
    ) -> None:
        """Process transaction and emit appropriate events."""
        logs = tx_details.get("meta", {}).get("logMessages", [])
        timestamp = tx_details.get("blockTime")
        
        # Parse events from logs
        for log in logs:
            event = self._parse_log_event(log, signature, slot, timestamp)
            if event:
                await self._emit_event(event)
                await self._update_db_from_event(event)
    
    def _parse_log_event(
        self,
        log: str,
        signature: str,
        slot: int,
        timestamp: Optional[int],
    ) -> Optional[BlockchainEvent]:
        """Parse event from program log."""
        # Look for program events
        event_markers = {
            "BountyCreated": EventType.BOUNTY_CREATED,
            "WorkSubmitted": EventType.WORK_SUBMITTED,
            "WorkApproved": EventType.WORK_APPROVED,
            "DisputeRaised": EventType.DISPUTE_RAISED,
        }
        
        for marker, event_type in event_markers.items():
            if marker in log:
                # Parse event data from log
                try:
                    # Extract JSON data after marker
                    data_start = log.find(marker) + len(marker)
                    data_str = log[data_start:].strip()
                    event_data = json.loads(data_str) if data_str else {}
                    
                    return BlockchainEvent(
                        event_type=event_type,
                        signature=signature,
                        slot=slot,
                        timestamp=timestamp,
                        data=event_data,
                    )
                except json.JSONDecodeError:
                    return BlockchainEvent(
                        event_type=event_type,
                        signature=signature,
                        slot=slot,
                        timestamp=timestamp,
                        data={"raw_log": log},
                    )
        
        return None
    
    async def _update_db_from_event(self, event: BlockchainEvent) -> None:
        """Update PostgreSQL based on blockchain event."""
        if event.event_type == EventType.WORK_APPROVED:
            # Update agent balance for approved work
            agent_pubkey = event.data.get("agent")
            reward = Decimal(str(event.data.get("reward", 0)))
            
            if agent_pubkey and reward > 0:
                # Find user by wallet address
                query = "SELECT user_id FROM token_balances WHERE wallet_address = $1"
                row = await self.db.fetchrow(query, agent_pubkey)
                
                if row:
                    await self.sync_balance(row["user_id"])
    
    def stop_event_listener(self) -> None:
        """Stop the event listener."""
        self._running = False
        logger.info("Event listener stopped")
    
    # ========== Reconciliation ==========
    
    async def reconcile_all_balances(
        self,
        batch_size: int = 100,
    ) -> dict[str, Any]:
        """
        Reconcile all database balances with blockchain.
        
        Args:
            batch_size: Number of accounts to process per batch
            
        Returns:
            Reconciliation report
        """
        report = {
            "total_checked": 0,
            "mismatches_found": 0,
            "synced": 0,
            "errors": [],
        }
        
        query = """
            SELECT user_id FROM token_balances
            ORDER BY last_synced_at NULLS FIRST
        """
        
        rows = await self.db.fetch(query)
        
        for row in rows:
            try:
                report["total_checked"] += 1
                before = await self.get_balance_from_db(row["user_id"])
                
                if before:
                    after = await self.sync_balance(row["user_id"])
                    if before.balance != after.balance:
                        report["mismatches_found"] += 1
                    report["synced"] += 1
                    
            except Exception as e:
                report["errors"].append({
                    "user_id": str(row["user_id"]),
                    "error": str(e),
                })
        
        return report


class BridgeManager:
    """
    High-level manager for bridge operations.
    
    Provides simplified interface for common operations
    and handles connection lifecycle.
    """
    
    def __init__(
        self,
        solana_rpc_url: str,
        database_url: str,
        program_id: str,
        mint_address: str,
        treasury_wallet: str,
    ):
        self.solana_rpc_url = solana_rpc_url
        self.database_url = database_url
        self.program_id = program_id
        self.mint_address = mint_address
        self.treasury_wallet = treasury_wallet
        self._rpc: Optional[SolanaRPCClient] = None
        self._db_pool: Optional[Pool] = None
        self._bridge: Optional[TokenBridge] = None
        
    async def initialize(self) -> None:
        """Initialize all connections."""
        # Initialize RPC client
        self._rpc = SolanaRPCClient(self.solana_rpc_url)
        
        # Initialize database pool
        self._db_pool = await asyncpg.create_pool(
            self.database_url,
            min_size=5,
            max_size=20,
        )
        
        # Initialize bridge
        self._bridge = TokenBridge(
            rpc_client=self._rpc,
            db_pool=self._db_pool,
            program_id=self.program_id,
            mint_address=self.mint_address,
            treasury_wallet=self.treasury_wallet,
        )
        
        logger.info("Bridge manager initialized")
    
    async def close(self) -> None:
        """Close all connections."""
        if self._bridge:
            self._bridge.stop_event_listener()
        
        if self._rpc:
            await self._rpc.close()
        
        if self._db_pool:
            await self._db_pool.close()
        
        logger.info("Bridge manager closed")
    
    @property
    def bridge(self) -> TokenBridge:
        """Get token bridge instance."""
        if not self._bridge:
            raise BridgeError("Bridge not initialized")
        return self._bridge
    
    async def get_user_balance(self, user_id: UUID) -> Optional[TokenBalance]:
        """Get user balance (syncs with chain first)."""
        return await self.bridge.sync_balance(user_id)
    
    async def deposit_to_blockchain(
        self,
        user_id: UUID,
        amount: Decimal,
        authority_keypair: Keypair,
    ) -> TransactionResult:
        """
        Deposit tokens from treasury to user's blockchain wallet.
        
        This represents the on-chain portion of a deposit operation.
        """
        balance = await self.bridge.get_balance_from_db(user_id)
        if not balance:
            raise BridgeError(f"User {user_id} not found")
        
        result = await self.bridge.mint_tokens(
            balance.wallet_address,
            amount,
            authority_keypair,
        )
        
        if result.success:
            await self.bridge.sync_balance(user_id)
        
        return result
    
    async def withdraw_from_blockchain(
        self,
        user_id: UUID,
        amount: Decimal,
        user_keypair: Keypair,
    ) -> TransactionResult:
        """
        Withdraw tokens from user's wallet to treasury.
        
        This burns tokens on-chain and credits PostgreSQL.
        """
        balance = await self.bridge.get_balance_from_db(user_id)
        if not balance:
            raise BridgeError(f"User {user_id} not found")
        
        # Transfer to treasury (represents burn/withdrawal)
        result = await self.bridge.transfer_tokens(
            balance.wallet_address,
            self.treasury_wallet,
            amount,
            user_keypair,
        )
        
        if result.success:
            await self.bridge.sync_balance(user_id)
        
        return result


# ========== Database Schema Helpers ==========

BRIDGE_DB_SCHEMA = """
-- Token balances table (synced with blockchain)
CREATE TABLE IF NOT EXISTS token_balances (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    wallet_address VARCHAR(44) NOT NULL UNIQUE,
    balance NUMERIC(20, 6) NOT NULL DEFAULT 0,
    staked_amount NUMERIC(20, 6) NOT NULL DEFAULT 0,
    pending_rewards NUMERIC(20, 6) NOT NULL DEFAULT 0,
    last_synced_at TIMESTAMPTZ,
    chain_version INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Transaction audit log
CREATE TABLE IF NOT EXISTS token_transactions (
    id SERIAL PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    tx_type VARCHAR(20) NOT NULL,  -- 'deposit', 'withdraw', 'stake', 'unstake', 'reward'
    amount NUMERIC(20, 6) NOT NULL,
    signature VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',  -- 'pending', 'confirmed', 'failed'
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confirmed_at TIMESTAMPTZ
);

-- Bridge sync log for debugging
CREATE TABLE IF NOT EXISTS bridge_sync_log (
    id SERIAL PRIMARY KEY,
    operation VARCHAR(50) NOT NULL,
    user_id UUID,
    details JSONB,
    success BOOLEAN NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_token_balances_wallet ON token_balances(wallet_address);
CREATE INDEX IF NOT EXISTS idx_token_transactions_user ON token_transactions(user_id);
CREATE INDEX IF NOT EXISTS idx_token_transactions_signature ON token_transactions(signature);
CREATE INDEX IF NOT EXISTS idx_bridge_sync_user ON bridge_sync_log(user_id);
"""


async def init_bridge_schema(db_pool: Pool) -> None:
    """Initialize database schema for bridge."""
    async with db_pool.acquire() as conn:
        await conn.execute(BRIDGE_DB_SCHEMA)
    logger.info("Bridge database schema initialized")


# ========== Example Usage ==========

async def example_usage():
    """Example of how to use the bridge module."""
    from uuid import uuid4
    
    # Configuration
    config = {
        "solana_rpc_url": "https://api.devnet.solana.com",
        "database_url": "postgresql://user:pass@localhost/agentwork",
        "program_id": "AGWRK11111111111111111111111111111111111111",
        "mint_address": "Mint111111111111111111111111111111111111111",
        "treasury_wallet": "Treasury111111111111111111111111111111111111",
    }
    
    # Initialize manager
    manager = BridgeManager(**config)
    await manager.initialize()
    
    try:
        # Register event handler
        def on_work_approved(event: BlockchainEvent):
            print(f"Work approved! {event.data}")
        
        manager.bridge.on_event(EventType.WORK_APPROVED, on_work_approved)
        
        # Start event listener in background
        listener_task = asyncio.create_task(
            manager.bridge.start_event_listener(poll_interval=5.0)
        )
        
        # Get user balance (auto-syncs with chain)
        user_id = uuid4()
        balance = await manager.get_user_balance(user_id)
        
        if balance:
            print(f"Balance: {balance.balance} AGWRK")
        
        # Run for a bit
        await asyncio.sleep(60)
        
        # Stop listener
        manager.bridge.stop_event_listener()
        await listener_task
        
    finally:
        await manager.close()


if __name__ == "__main__":
    # Run example
    asyncio.run(example_usage())
