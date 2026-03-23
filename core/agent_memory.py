"""
Working Memory, Hypothesis, and Evidence models for the Agentic Brain.
These structures evolve during an investigation — the agent's "scratchpad".
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime


class HypothesisCategory(str, Enum):
    THERMAL = "thermal"
    POWER = "power"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    FIRMWARE = "firmware"
    CPU = "cpu"
    SYSTEM = "system"


class EvidenceStrength(str, Enum):
    STRONG = "strong"       # Directly confirms/refutes
    MODERATE = "moderate"   # Correlates but not conclusive
    WEAK = "weak"           # Tangentially related


@dataclass
class Fact:
    """A confirmed piece of information discovered during investigation."""
    id: str
    description: str
    component: str           # e.g. "Fan.Embedded.1A"
    metric: Optional[str] = None   # e.g. "temperature", "speed_rpm"
    value: Optional[Any] = None    # e.g. 77.0
    unit: Optional[str] = None     # e.g. "°C", "RPM"
    status: str = "ok"       # ok, warning, critical
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "component": self.component, "metric": self.metric,
            "value": self.value, "unit": self.unit, "status": self.status,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class Evidence:
    """A piece of evidence supporting or refuting a hypothesis."""
    fact_id: str
    description: str
    supports: bool           # True = supports hypothesis, False = refutes
    strength: EvidenceStrength = EvidenceStrength.MODERATE

    def to_dict(self) -> dict:
        return {
            "fact_id": self.fact_id, "description": self.description,
            "supports": self.supports, "strength": self.strength.value,
        }


@dataclass
class Hypothesis:
    """A candidate root-cause the agent is testing."""
    id: str
    description: str
    category: HypothesisCategory
    confidence: float = 0.5     # 0.0 – 1.0
    supporting_evidence: List[Evidence] = field(default_factory=list)
    refuting_evidence: List[Evidence] = field(default_factory=list)
    next_tool: Optional[str] = None       # tool to run next to test this
    resolution_workflow: Optional[str] = None  # Dell workflow key if confirmed
    ruled_out: bool = False
    confirmed: bool = False

    def adjust_confidence(self, delta: float):
        self.confidence = max(0.0, min(1.0, self.confidence + delta))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "description": self.description,
            "category": self.category.value,
            "confidence": round(self.confidence, 2),
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "refuting_evidence": [e.to_dict() for e in self.refuting_evidence],
            "next_tool": self.next_tool,
            "resolution_workflow": self.resolution_workflow,
            "ruled_out": self.ruled_out, "confirmed": self.confirmed,
        }


@dataclass
class TimelineEvent:
    """An event on the investigation timeline."""
    timestamp: datetime
    description: str
    severity: str = "info"   # info, warning, critical
    source: str = ""         # e.g. "SEL", "sensor", "agent"

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "description": self.description,
            "severity": self.severity, "source": self.source,
        }


@dataclass
class Thought:
    """One step in the agent's reasoning chain — visible to the user."""
    step: int
    reasoning: str
    hypotheses_snapshot: List[dict] = field(default_factory=list)  # [{id, desc, confidence}]
    next_action: Optional[str] = None     # tool name the agent will run next
    next_action_reason: Optional[str] = None
    conclusion: Optional[str] = None       # non-None = agent is done
    ruled_out: List[str] = field(default_factory=list)  # hypothesis IDs ruled out this step

    def to_dict(self) -> dict:
        return {
            "step": self.step, "reasoning": self.reasoning,
            "hypotheses": self.hypotheses_snapshot,
            "next_action": self.next_action,
            "next_action_reason": self.next_action_reason,
            "conclusion": self.conclusion,
            "ruled_out": self.ruled_out,
        }


class WorkingMemory:
    """
    The agent's evolving knowledge during an investigation.
    Updated after every observe step.
    """

    def __init__(self):
        self.facts: Dict[str, Fact] = {}
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.timeline: List[TimelineEvent] = []
        self.open_questions: List[str] = []
        self.thought_chain: List[Thought] = []
        self.tools_used: List[str] = []
        self.raw_data: Dict[str, Any] = {}   # tool_name → raw result

    # ── Fact management ───────────────────────────────────────
    def add_fact(self, fact: Fact):
        self.facts[fact.id] = fact

    def get_facts_by_component(self, component_prefix: str) -> List[Fact]:
        return [f for f in self.facts.values() if f.component.lower().startswith(component_prefix.lower())]

    def get_facts_by_status(self, status: str) -> List[Fact]:
        return [f for f in self.facts.values() if f.status == status]

    # ── Hypothesis management ─────────────────────────────────
    def add_hypothesis(self, hyp: Hypothesis):
        self.hypotheses[hyp.id] = hyp

    def get_active_hypotheses(self) -> List[Hypothesis]:
        """Ranked by confidence, excluding ruled-out."""
        active = [h for h in self.hypotheses.values() if not h.ruled_out]
        return sorted(active, key=lambda h: h.confidence, reverse=True)

    def get_top_hypothesis(self) -> Optional[Hypothesis]:
        active = self.get_active_hypotheses()
        return active[0] if active else None

    def rule_out(self, hyp_id: str, reason: str):
        if hyp_id in self.hypotheses:
            self.hypotheses[hyp_id].ruled_out = True
            self.hypotheses[hyp_id].refuting_evidence.append(
                Evidence(fact_id="rule_out", description=reason, supports=False, strength=EvidenceStrength.STRONG)
            )

    def confirm(self, hyp_id: str):
        if hyp_id in self.hypotheses:
            self.hypotheses[hyp_id].confirmed = True
            self.hypotheses[hyp_id].confidence = 1.0

    # ── Summaries ─────────────────────────────────────────────
    def summary(self) -> dict:
        return {
            "facts_count": len(self.facts),
            "active_hypotheses": [
                {"id": h.id, "description": h.description, "confidence": round(h.confidence, 2)}
                for h in self.get_active_hypotheses()
            ],
            "ruled_out": [h.id for h in self.hypotheses.values() if h.ruled_out],
            "confirmed": [h.id for h in self.hypotheses.values() if h.confirmed],
            "open_questions": self.open_questions,
            "tools_used": self.tools_used,
            "critical_facts": [f.to_dict() for f in self.get_facts_by_status("critical")],
            "warning_facts": [f.to_dict() for f in self.get_facts_by_status("warning")],
        }

    def to_dict(self) -> dict:
        return {
            "facts": {k: v.to_dict() for k, v in self.facts.items()},
            "hypotheses": {k: v.to_dict() for k, v in self.hypotheses.items()},
            "timeline": [t.to_dict() for t in self.timeline],
            "thought_chain": [t.to_dict() for t in self.thought_chain],
            "open_questions": self.open_questions,
            "tools_used": self.tools_used,
        }
