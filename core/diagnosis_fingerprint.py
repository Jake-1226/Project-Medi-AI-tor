"""
Diagnosis Fingerprinting — Pattern-based learning without ML.

Creates a fingerprint (hash) of each diagnosis based on:
- Symptom pattern (which subsystems had anomalies)
- Evidence pattern (which tools found what)
- Conclusion (root cause + remediation)

When a new investigation matches a known fingerprint, the system
returns the cached diagnosis INSTANTLY without re-running the
full reasoning loop. The system gets smarter over time without
any machine learning or neural network.

Patent relevance: "Method for hardware failure pattern recognition
and instant diagnosis recall using deterministic fingerprinting,
without machine learning model training or inference."
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

FINGERPRINT_STORE = os.path.join(os.path.dirname(__file__), '..', 'data', 'fingerprints.json')


@dataclass
class SymptomVector:
    """Normalized representation of observed symptoms."""
    thermal_anomaly: bool = False
    power_anomaly: bool = False
    memory_anomaly: bool = False
    storage_anomaly: bool = False
    network_anomaly: bool = False
    firmware_anomaly: bool = False
    cpu_anomaly: bool = False
    fan_anomaly: bool = False
    # Severity levels (0=normal, 1=warning, 2=critical)
    thermal_severity: int = 0
    power_severity: int = 0
    memory_severity: int = 0
    storage_severity: int = 0

    def to_tuple(self) -> tuple:
        return (
            self.thermal_anomaly, self.power_anomaly, self.memory_anomaly,
            self.storage_anomaly, self.network_anomaly, self.firmware_anomaly,
            self.cpu_anomaly, self.fan_anomaly,
            self.thermal_severity, self.power_severity,
            self.memory_severity, self.storage_severity,
        )

    def to_dict(self) -> dict:
        return {
            "thermal": {"anomaly": self.thermal_anomaly, "severity": self.thermal_severity},
            "power": {"anomaly": self.power_anomaly, "severity": self.power_severity},
            "memory": {"anomaly": self.memory_anomaly, "severity": self.memory_severity},
            "storage": {"anomaly": self.storage_anomaly, "severity": self.storage_severity},
            "network": {"anomaly": self.network_anomaly},
            "firmware": {"anomaly": self.firmware_anomaly},
            "cpu": {"anomaly": self.cpu_anomaly},
            "fan": {"anomaly": self.fan_anomaly},
        }


@dataclass
class DiagnosisRecord:
    """A stored diagnosis with its fingerprint."""
    fingerprint: str                    # SHA-256 of symptom + evidence pattern
    symptom_vector: Dict[str, Any]
    root_cause: str
    diagnosis: str
    remediation: str
    confidence: float
    tools_used: List[str]
    investigation_duration_ms: int
    occurrence_count: int = 1           # How many times this pattern matched
    first_seen: str = ""
    last_seen: str = ""
    server_models: List[str] = field(default_factory=list)  # Which models hit this


class DiagnosisFingerprinter:
    """
    Creates and matches diagnosis fingerprints for instant recall.

    When the agent completes an investigation, we:
    1. Extract the symptom vector (which subsystems had anomalies)
    2. Hash it into a fingerprint
    3. Store the fingerprint → diagnosis mapping

    On new investigations, we:
    1. Extract symptoms from initial data
    2. Check against known fingerprints
    3. If match found → return cached diagnosis instantly (skip full loop)

    The system gets smarter with every diagnosis — WITHOUT any ML.
    """

    def __init__(self, store_path: Optional[str] = None):
        self.store_path = store_path or FINGERPRINT_STORE
        self.fingerprints: OrderedDict[str, DiagnosisRecord] = OrderedDict()
        self.max_fingerprints = 10000
        self._load_store()

    def _load_store(self):
        """Load fingerprints from persistent storage."""
        try:
            if os.path.exists(self.store_path):
                with open(self.store_path, 'r') as f:
                    data = json.load(f)
                for fp_data in data.get('fingerprints', []):
                    rec = DiagnosisRecord(
                        fingerprint=fp_data['fingerprint'],
                        symptom_vector=fp_data['symptom_vector'],
                        root_cause=fp_data['root_cause'],
                        diagnosis=fp_data['diagnosis'],
                        remediation=fp_data['remediation'],
                        confidence=fp_data['confidence'],
                        tools_used=fp_data['tools_used'],
                        investigation_duration_ms=fp_data['investigation_duration_ms'],
                        occurrence_count=fp_data.get('occurrence_count', 1),
                        first_seen=fp_data.get('first_seen', ''),
                        last_seen=fp_data.get('last_seen', ''),
                        server_models=fp_data.get('server_models', []),
                    )
                    self.fingerprints[rec.fingerprint] = rec
                logger.info(f"Loaded {len(self.fingerprints)} diagnosis fingerprints")
        except Exception as e:
            logger.warning(f"Could not load fingerprint store: {e}")

    def _save_store(self):
        """Persist fingerprints to disk."""
        try:
            os.makedirs(os.path.dirname(self.store_path), exist_ok=True)
            data = {
                'version': 1,
                'updated_at': datetime.now(timezone.utc).isoformat(),
                'count': len(self.fingerprints),
                'fingerprints': [
                    {
                        'fingerprint': r.fingerprint,
                        'symptom_vector': r.symptom_vector,
                        'root_cause': r.root_cause,
                        'diagnosis': r.diagnosis,
                        'remediation': r.remediation,
                        'confidence': r.confidence,
                        'tools_used': r.tools_used,
                        'investigation_duration_ms': r.investigation_duration_ms,
                        'occurrence_count': r.occurrence_count,
                        'first_seen': r.first_seen,
                        'last_seen': r.last_seen,
                        'server_models': r.server_models,
                    }
                    for r in self.fingerprints.values()
                ],
            }
            with open(self.store_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save fingerprint store: {e}")

    # ── Fingerprint Generation ──

    def generate_fingerprint(self, symptoms: SymptomVector) -> str:
        """Generate a SHA-256 fingerprint from a symptom vector."""
        raw = json.dumps(symptoms.to_tuple(), sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def extract_symptoms(self, facts: List[Dict]) -> SymptomVector:
        """Extract a symptom vector from collected facts."""
        sv = SymptomVector()
        for fact in facts:
            component = fact.get('component', '').lower()
            status = fact.get('status', 'ok').lower()
            severity = 2 if status == 'critical' else (1 if status == 'warning' else 0)

            if any(k in component for k in ['temp', 'thermal', 'inlet']):
                sv.thermal_anomaly = severity > 0
                sv.thermal_severity = max(sv.thermal_severity, severity)
            elif any(k in component for k in ['fan', 'cooling']):
                sv.fan_anomaly = severity > 0
            elif any(k in component for k in ['psu', 'power', 'voltage']):
                sv.power_anomaly = severity > 0
                sv.power_severity = max(sv.power_severity, severity)
            elif any(k in component for k in ['dimm', 'memory', 'ram', 'ecc']):
                sv.memory_anomaly = severity > 0
                sv.memory_severity = max(sv.memory_severity, severity)
            elif any(k in component for k in ['disk', 'drive', 'ssd', 'hdd', 'raid', 'storage']):
                sv.storage_anomaly = severity > 0
                sv.storage_severity = max(sv.storage_severity, severity)
            elif any(k in component for k in ['nic', 'network', 'ethernet', 'port']):
                sv.network_anomaly = severity > 0
            elif any(k in component for k in ['bios', 'firmware', 'idrac']):
                sv.firmware_anomaly = severity > 0
            elif any(k in component for k in ['cpu', 'processor']):
                sv.cpu_anomaly = severity > 0
        return sv

    # ── Matching ──

    def match(self, symptoms: SymptomVector) -> Optional[DiagnosisRecord]:
        """Check if we've seen this symptom pattern before."""
        fp = self.generate_fingerprint(symptoms)
        if fp in self.fingerprints:
            record = self.fingerprints[fp]
            record.occurrence_count += 1
            record.last_seen = datetime.now(timezone.utc).isoformat()
            self._save_store()
            logger.info(f"Fingerprint match! Pattern seen {record.occurrence_count} times: {record.root_cause}")
            return record
        return None

    def fuzzy_match(self, symptoms: SymptomVector, threshold: float = 0.8) -> Optional[Tuple[DiagnosisRecord, float]]:
        """Find closest matching fingerprint using similarity score."""
        target = symptoms.to_tuple()
        best_match = None
        best_score = 0.0

        for record in self.fingerprints.values():
            stored_sv = self._reconstruct_vector(record.symptom_vector)
            stored_tuple = stored_sv.to_tuple()
            score = self._similarity(target, stored_tuple)
            if score > best_score:
                best_score = score
                best_match = record

        if best_match and best_score >= threshold:
            return (best_match, best_score)
        return None

    def _similarity(self, a: tuple, b: tuple) -> float:
        """Calculate similarity between two symptom vectors."""
        if len(a) != len(b):
            return 0.0
        matches = sum(1 for x, y in zip(a, b) if x == y)
        return matches / len(a)

    def _reconstruct_vector(self, sv_dict: Dict) -> SymptomVector:
        """Reconstruct a SymptomVector from stored dict."""
        sv = SymptomVector()
        for key, val in sv_dict.items():
            if isinstance(val, dict):
                setattr(sv, f"{key}_anomaly", val.get("anomaly", False))
                if "severity" in val:
                    setattr(sv, f"{key}_severity", val.get("severity", 0))
            elif isinstance(val, bool):
                setattr(sv, f"{key}_anomaly", val)
        return sv

    # ── Recording ──

    def record_diagnosis(self, symptoms: SymptomVector, root_cause: str,
                         diagnosis: str, remediation: str, confidence: float,
                         tools_used: List[str], duration_ms: int,
                         server_model: Optional[str] = None) -> str:
        """Record a completed diagnosis as a fingerprint."""
        fp = self.generate_fingerprint(symptoms)
        now = datetime.now(timezone.utc).isoformat()

        if fp in self.fingerprints:
            # Update existing
            record = self.fingerprints[fp]
            record.occurrence_count += 1
            record.last_seen = now
            if server_model and server_model not in record.server_models:
                record.server_models.append(server_model)
            # Update confidence if higher
            if confidence > record.confidence:
                record.confidence = confidence
                record.diagnosis = diagnosis
                record.remediation = remediation
        else:
            # New fingerprint
            record = DiagnosisRecord(
                fingerprint=fp,
                symptom_vector=symptoms.to_dict(),
                root_cause=root_cause,
                diagnosis=diagnosis,
                remediation=remediation,
                confidence=confidence,
                tools_used=tools_used,
                investigation_duration_ms=duration_ms,
                occurrence_count=1,
                first_seen=now,
                last_seen=now,
                server_models=[server_model] if server_model else [],
            )
            self.fingerprints[fp] = record

            # Evict oldest if over limit
            while len(self.fingerprints) > self.max_fingerprints:
                self.fingerprints.popitem(last=False)

        self._save_store()
        logger.info(f"Recorded fingerprint {fp}: {root_cause}")
        return fp

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        """Get fingerprint store statistics."""
        if not self.fingerprints:
            return {"total": 0, "top_patterns": []}

        sorted_by_count = sorted(
            self.fingerprints.values(),
            key=lambda r: r.occurrence_count,
            reverse=True,
        )

        return {
            "total_fingerprints": len(self.fingerprints),
            "total_matches": sum(r.occurrence_count for r in self.fingerprints.values()),
            "top_patterns": [
                {
                    "fingerprint": r.fingerprint,
                    "root_cause": r.root_cause,
                    "occurrences": r.occurrence_count,
                    "confidence": r.confidence,
                    "server_models": r.server_models,
                }
                for r in sorted_by_count[:10]
            ],
        }
