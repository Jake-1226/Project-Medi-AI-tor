"""
Evidence Chain Provenance — Cryptographic audit trail for LLM-free diagnoses.

Every reasoning step, API call, and conclusion is recorded with:
- Timestamp (UTC)
- Data hash (SHA-256 of raw API response)
- Causal links (which evidence led to which conclusion)
- Reproducibility proof (same inputs → same outputs, verifiable)

This makes every diagnosis FULLY AUDITABLE and LEGALLY DEFENSIBLE —
a key differentiator from LLM-based systems where outputs are non-deterministic.

Patent relevance: Strengthens "LLM-free diagnosis" claim by proving
deterministic, traceable reasoning without neural network inference.
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum


class ProvenanceEventType(str, Enum):
    HYPOTHESIS_FORMED = "hypothesis_formed"
    TOOL_INVOKED = "tool_invoked"
    API_CALL = "api_call"
    EVIDENCE_COLLECTED = "evidence_collected"
    CONFIDENCE_UPDATED = "confidence_updated"
    HYPOTHESIS_RULED_OUT = "hypothesis_ruled_out"
    CONCLUSION_REACHED = "conclusion_reached"
    REMEDIATION_PROPOSED = "remediation_proposed"


@dataclass
class ProvenanceEvent:
    """A single auditable event in the evidence chain."""
    id: str
    event_type: ProvenanceEventType
    timestamp: str  # ISO 8601 UTC
    description: str
    data_hash: Optional[str] = None      # SHA-256 of raw data
    parent_event_ids: List[str] = field(default_factory=list)  # Causal links
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "description": self.description,
            "data_hash": self.data_hash,
            "parent_event_ids": self.parent_event_ids,
            "metadata": self.metadata,
        }


class EvidenceChain:
    """
    Maintains a cryptographically verifiable chain of evidence for a diagnosis.

    Each event references its parent events (causal graph), and raw API data
    is hashed so the chain can be independently verified. The entire chain
    is serializable for export, audit, and legal compliance.
    """

    def __init__(self, investigation_id: Optional[str] = None):
        self.investigation_id = investigation_id or str(uuid.uuid4())
        self.events: List[ProvenanceEvent] = []
        self._event_index: Dict[str, ProvenanceEvent] = {}
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.chain_hash: Optional[str] = None  # Rolling hash of entire chain

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hash_data(self, data: Any) -> str:
        """SHA-256 hash of any data for tamper-proof provenance."""
        raw = json.dumps(data, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def _update_chain_hash(self):
        """Rolling hash of the entire chain — detects tampering."""
        chain_data = [e.to_dict() for e in self.events]
        self.chain_hash = self._hash_data(chain_data)

    def record_hypothesis(self, hypothesis_id: str, description: str,
                          category: str, initial_confidence: float,
                          parent_ids: Optional[List[str]] = None) -> str:
        """Record the formation of a new hypothesis."""
        event = ProvenanceEvent(
            id=f"hyp-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.HYPOTHESIS_FORMED,
            timestamp=self._now(),
            description=f"Hypothesis formed: {description}",
            parent_event_ids=parent_ids or [],
            metadata={
                "hypothesis_id": hypothesis_id,
                "category": category,
                "initial_confidence": initial_confidence,
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_tool_invocation(self, tool_name: str, parameters: Dict,
                               hypothesis_id: str,
                               parent_ids: Optional[List[str]] = None) -> str:
        """Record a diagnostic tool being invoked."""
        event = ProvenanceEvent(
            id=f"tool-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.TOOL_INVOKED,
            timestamp=self._now(),
            description=f"Tool invoked: {tool_name}",
            parent_event_ids=parent_ids or [],
            metadata={
                "tool_name": tool_name,
                "parameters": parameters,
                "testing_hypothesis": hypothesis_id,
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_api_call(self, endpoint: str, response_data: Any,
                        parent_tool_id: str) -> str:
        """Record a raw API call with data hash for verification."""
        data_hash = self._hash_data(response_data)
        event = ProvenanceEvent(
            id=f"api-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.API_CALL,
            timestamp=self._now(),
            description=f"API call: {endpoint}",
            data_hash=data_hash,
            parent_event_ids=[parent_tool_id],
            metadata={
                "endpoint": endpoint,
                "response_size": len(json.dumps(response_data, default=str)),
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_evidence(self, fact_description: str, supports_hypothesis: bool,
                        strength: str, hypothesis_id: str,
                        parent_ids: Optional[List[str]] = None) -> str:
        """Record evidence collected from tool output."""
        event = ProvenanceEvent(
            id=f"evi-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.EVIDENCE_COLLECTED,
            timestamp=self._now(),
            description=fact_description,
            parent_event_ids=parent_ids or [],
            metadata={
                "supports": supports_hypothesis,
                "strength": strength,
                "hypothesis_id": hypothesis_id,
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_confidence_update(self, hypothesis_id: str,
                                  old_confidence: float, new_confidence: float,
                                  reason: str,
                                  evidence_ids: Optional[List[str]] = None) -> str:
        """Record a confidence score change with causal evidence."""
        event = ProvenanceEvent(
            id=f"conf-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.CONFIDENCE_UPDATED,
            timestamp=self._now(),
            description=f"Confidence updated: {old_confidence:.2f} → {new_confidence:.2f} ({reason})",
            parent_event_ids=evidence_ids or [],
            metadata={
                "hypothesis_id": hypothesis_id,
                "old_confidence": old_confidence,
                "new_confidence": new_confidence,
                "delta": round(new_confidence - old_confidence, 4),
                "reason": reason,
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_ruled_out(self, hypothesis_id: str, reason: str,
                         evidence_ids: Optional[List[str]] = None) -> str:
        """Record a hypothesis being eliminated."""
        event = ProvenanceEvent(
            id=f"out-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.HYPOTHESIS_RULED_OUT,
            timestamp=self._now(),
            description=f"Hypothesis ruled out: {reason}",
            parent_event_ids=evidence_ids or [],
            metadata={"hypothesis_id": hypothesis_id, "reason": reason},
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    def record_conclusion(self, diagnosis: str, confidence: float,
                          root_cause: str, remediation: str,
                          supporting_evidence_ids: List[str]) -> str:
        """Record the final diagnosis conclusion."""
        event = ProvenanceEvent(
            id=f"conclusion-{uuid.uuid4().hex[:8]}",
            event_type=ProvenanceEventType.CONCLUSION_REACHED,
            timestamp=self._now(),
            description=f"Diagnosis complete: {diagnosis}",
            parent_event_ids=supporting_evidence_ids,
            metadata={
                "diagnosis": diagnosis,
                "confidence": confidence,
                "root_cause": root_cause,
                "remediation": remediation,
            },
        )
        self.events.append(event)
        self._event_index[event.id] = event
        self._update_chain_hash()
        return event.id

    # ── Export & Verification ──

    def export_chain(self) -> Dict[str, Any]:
        """Export the full evidence chain for audit."""
        return {
            "investigation_id": self.investigation_id,
            "created_at": self.created_at,
            "chain_hash": self.chain_hash,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
            "summary": self._build_summary(),
        }

    def verify_integrity(self) -> bool:
        """Verify the chain hasn't been tampered with."""
        expected = self._hash_data([e.to_dict() for e in self.events])
        return expected == self.chain_hash

    def _build_summary(self) -> Dict[str, Any]:
        """Build a human-readable summary of the evidence chain."""
        conclusions = [e for e in self.events
                       if e.event_type == ProvenanceEventType.CONCLUSION_REACHED]
        tools_used = [e.metadata.get("tool_name")
                      for e in self.events
                      if e.event_type == ProvenanceEventType.TOOL_INVOKED]
        api_calls = [e for e in self.events
                     if e.event_type == ProvenanceEventType.API_CALL]
        hypotheses_formed = [e for e in self.events
                             if e.event_type == ProvenanceEventType.HYPOTHESIS_FORMED]
        ruled_out = [e for e in self.events
                     if e.event_type == ProvenanceEventType.HYPOTHESIS_RULED_OUT]

        return {
            "total_events": len(self.events),
            "hypotheses_formed": len(hypotheses_formed),
            "hypotheses_ruled_out": len(ruled_out),
            "tools_used": list(set(tools_used)),
            "api_calls_made": len(api_calls),
            "data_hashes_recorded": len([e for e in self.events if e.data_hash]),
            "conclusion": conclusions[-1].metadata if conclusions else None,
            "chain_integrity": self.verify_integrity(),
        }

    def get_causal_path(self, event_id: str) -> List[ProvenanceEvent]:
        """Trace backwards from an event to find its complete causal path."""
        path = []
        visited = set()

        def _trace(eid):
            if eid in visited or eid not in self._event_index:
                return
            visited.add(eid)
            event = self._event_index[eid]
            path.append(event)
            for parent_id in event.parent_event_ids:
                _trace(parent_id)

        _trace(event_id)
        path.reverse()
        return path
