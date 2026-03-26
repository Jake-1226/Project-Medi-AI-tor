"""
Session Handoff Protocol — Secure transfer of investigation state between technicians.

Allows Technician A to hand off their entire session (connection state,
investigation history, working memory, evidence chain) to Technician B
via a time-limited, single-use handoff token.

Patent relevance: "Method for secure transfer of diagnostic session state
between authenticated users in a server management system, including
connection binding, investigation context, and evidence chain continuity."
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class HandoffStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


@dataclass
class HandoffToken:
    """A time-limited, single-use token for session transfer."""
    token: str
    from_session_id: str
    from_username: str
    to_username: Optional[str]           # None = any authenticated user
    created_at: str
    expires_at: str
    status: HandoffStatus = HandoffStatus.PENDING
    accepted_by: Optional[str] = None
    accepted_at: Optional[str] = None
    notes: str = ""                      # Technician's handoff notes
    investigation_summary: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "token": self.token[:8] + "...",  # Truncated for display
            "from_username": self.from_username,
            "to_username": self.to_username or "(any)",
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "status": self.status.value,
            "accepted_by": self.accepted_by,
            "accepted_at": self.accepted_at,
            "notes": self.notes,
            "has_investigation": bool(self.investigation_summary),
        }


class SessionHandoffManager:
    """
    Manages secure session handoffs between technicians.

    Flow:
    1. Technician A calls POST /api/handoff/create with optional target user and notes
    2. System generates a time-limited token (default 15 min) containing the session reference
    3. Technician A shares the token with Technician B (verbally, via chat, etc.)
    4. Technician B calls POST /api/handoff/accept with the token
    5. System transfers Technician A's session to Technician B:
       - Connection state (which server, Redfish client)
       - Investigation history (working memory, hypotheses, evidence)
       - Evidence chain (full audit trail)
    6. Technician A's session is disconnected (single-owner)
    7. Handoff is logged in audit trail for compliance
    """

    def __init__(self, token_ttl_minutes: int = 15):
        self.token_ttl = timedelta(minutes=token_ttl_minutes)
        self.pending_handoffs: Dict[str, HandoffToken] = {}
        self.handoff_history: list = []
        self.max_history = 1000

    def create_handoff(self, from_session_id: str, from_username: str,
                       to_username: Optional[str] = None,
                       notes: str = "",
                       investigation_summary: Optional[Dict] = None) -> HandoffToken:
        """
        Create a new handoff token.

        Args:
            from_session_id: The session being handed off
            from_username: The technician initiating the handoff
            to_username: Optional target technician (None = any authenticated user)
            notes: Free-text notes about the investigation state
            investigation_summary: Optional summary of current investigation
        """
        now = datetime.now(timezone.utc)
        token_str = secrets.token_urlsafe(32)

        handoff = HandoffToken(
            token=token_str,
            from_session_id=from_session_id,
            from_username=from_username,
            to_username=to_username,
            created_at=now.isoformat(),
            expires_at=(now + self.token_ttl).isoformat(),
            notes=notes,
            investigation_summary=investigation_summary or {},
        )

        self.pending_handoffs[token_str] = handoff
        logger.info(f"Handoff created: {from_username} -> {to_username or 'any'} (expires {self.token_ttl})")
        return handoff

    def accept_handoff(self, token: str, accepting_username: str,
                       accepting_session_id: str) -> Optional[HandoffToken]:
        """
        Accept a handoff token and transfer the session.

        Returns the handoff token with updated status, or None if invalid.
        """
        handoff = self.pending_handoffs.get(token)
        if not handoff:
            logger.warning(f"Handoff token not found: {token[:8]}...")
            return None

        # Check expiry
        now = datetime.now(timezone.utc)
        expires = datetime.fromisoformat(handoff.expires_at)
        if now > expires:
            handoff.status = HandoffStatus.EXPIRED
            logger.warning(f"Handoff expired: {token[:8]}...")
            return None

        # Check if already used
        if handoff.status != HandoffStatus.PENDING:
            logger.warning(f"Handoff already {handoff.status.value}: {token[:8]}...")
            return None

        # Check target user restriction
        if handoff.to_username and handoff.to_username != accepting_username:
            logger.warning(f"Handoff restricted to {handoff.to_username}, not {accepting_username}")
            return None

        # Accept
        handoff.status = HandoffStatus.ACCEPTED
        handoff.accepted_by = accepting_username
        handoff.accepted_at = now.isoformat()

        # Remove from pending
        del self.pending_handoffs[token]

        # Add to history
        self.handoff_history.append(handoff.to_dict())
        if len(self.handoff_history) > self.max_history:
            self.handoff_history.pop(0)

        logger.info(f"Handoff accepted: {handoff.from_username} -> {accepting_username}")
        return handoff

    def cancel_handoff(self, token: str, username: str) -> bool:
        """Cancel a pending handoff (only the creator can cancel)."""
        handoff = self.pending_handoffs.get(token)
        if not handoff or handoff.from_username != username:
            return False
        handoff.status = HandoffStatus.CANCELLED
        del self.pending_handoffs[token]
        self.handoff_history.append(handoff.to_dict())
        logger.info(f"Handoff cancelled by {username}")
        return True

    def cleanup_expired(self):
        """Remove expired handoffs."""
        now = datetime.now(timezone.utc)
        expired = [
            t for t, h in self.pending_handoffs.items()
            if now > datetime.fromisoformat(h.expires_at)
        ]
        for t in expired:
            self.pending_handoffs[t].status = HandoffStatus.EXPIRED
            self.handoff_history.append(self.pending_handoffs[t].to_dict())
            del self.pending_handoffs[t]

    def get_pending_for_user(self, username: str) -> list:
        """Get all pending handoffs targeted at a specific user."""
        self.cleanup_expired()
        return [
            h.to_dict() for h in self.pending_handoffs.values()
            if h.to_username is None or h.to_username == username
        ]

    def get_history(self, limit: int = 50) -> list:
        """Get handoff history."""
        return self.handoff_history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """Get handoff system statistics."""
        return {
            "pending_handoffs": len(self.pending_handoffs),
            "total_completed": sum(1 for h in self.handoff_history if h.get("status") == "accepted"),
            "total_expired": sum(1 for h in self.handoff_history if h.get("status") == "expired"),
            "total_cancelled": sum(1 for h in self.handoff_history if h.get("status") == "cancelled"),
            "token_ttl_minutes": int(self.token_ttl.total_seconds() / 60),
        }
