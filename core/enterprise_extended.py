"""
Enterprise Extended Features — Medi-AI-tor
Addresses enterprise adoption gaps #31-#40:
  #31 Shift handoff
  #32 Knowledge base (past investigations)
  #33 Investigation sharing
  #34 Extended metric history
  #35 Per-server alert thresholds
  #36 PagerDuty/ServiceNow incident creation
  #37 SLA tracking
  #38 Guided onboarding
  #39 In-app glossary
  #40 Investigation report export (HTML)
"""

import logging
import json
import os
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)) or '.', 'data')


# ═══════════════════════════════════════════════════════════════
#  #31 — SHIFT HANDOFF
# ═══════════════════════════════════════════════════════════════

@dataclass
class ShiftHandoff:
    id: str
    from_user: str
    to_user: Optional[str]
    shift: str  # "day", "swing", "night"
    created_at: datetime
    summary: str
    open_issues: List[Dict[str, str]] = field(default_factory=list)
    server_notes: Dict[str, str] = field(default_factory=dict)  # server_id -> note
    priority_items: List[str] = field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None

class ShiftHandoffManager:
    """Pass context between shifts — ongoing issues, notes, priorities."""

    def __init__(self):
        self.handoffs: Dict[str, ShiftHandoff] = {}

    def create(self, from_user: str, shift: str, summary: str,
               open_issues: List[Dict] = None, server_notes: Dict[str, str] = None,
               priority_items: List[str] = None, to_user: str = None) -> ShiftHandoff:
        h = ShiftHandoff(
            id=str(uuid.uuid4())[:8], from_user=from_user, to_user=to_user,
            shift=shift, created_at=datetime.now(), summary=summary,
            open_issues=open_issues or [], server_notes=server_notes or {},
            priority_items=priority_items or [],
        )
        self.handoffs[h.id] = h
        logger.info(f"Shift handoff {h.id} created by {from_user} for {shift} shift")
        return h

    def acknowledge(self, handoff_id: str, username: str):
        h = self.handoffs.get(handoff_id)
        if not h:
            raise ValueError(f"Handoff {handoff_id} not found")
        h.acknowledged = True
        h.acknowledged_by = username
        h.acknowledged_at = datetime.now()

    def get_latest(self, shift: str = None) -> List[Dict]:
        result = []
        for h in sorted(self.handoffs.values(), key=lambda x: x.created_at, reverse=True):
            if shift and h.shift != shift:
                continue
            result.append({
                "id": h.id, "from_user": h.from_user, "to_user": h.to_user,
                "shift": h.shift, "summary": h.summary,
                "open_issues": h.open_issues, "server_notes": h.server_notes,
                "priority_items": h.priority_items,
                "created_at": h.created_at.isoformat(),
                "acknowledged": h.acknowledged, "acknowledged_by": h.acknowledged_by,
            })
        return result[:20]


# ═══════════════════════════════════════════════════════════════
#  #32 — KNOWLEDGE BASE (Past Investigations)
# ═══════════════════════════════════════════════════════════════

@dataclass
class KBArticle:
    id: str
    title: str
    root_cause: str
    symptoms: List[str]
    resolution: str
    server_model: Optional[str]
    category: str  # thermal, power, memory, storage, firmware, network
    confidence: float
    created_by: str
    created_at: datetime
    tags: List[str] = field(default_factory=list)
    sr_number: Optional[str] = None
    views: int = 0

class KnowledgeBaseManager:
    """Searchable knowledge base of past investigations and resolutions."""

    def __init__(self):
        self.articles: Dict[str, KBArticle] = {}
        self._file = os.path.join(_DATA_DIR, 'knowledge_base.jsonl')

    def add_from_investigation(self, diagnosis: Dict, created_by: str,
                                sr_number: str = None) -> KBArticle:
        """Auto-create KB article from an investigation diagnosis."""
        article = KBArticle(
            id=str(uuid.uuid4())[:8],
            title=diagnosis.get("root_cause", "Unknown issue"),
            root_cause=diagnosis.get("root_cause", ""),
            symptoms=[f.get("description", f.get("message", "")) for f in diagnosis.get("critical_findings", [])[:5]],
            resolution="\n".join(s.get("description", s.get("action", "")) for s in diagnosis.get("remediation_steps", [])[:5]),
            server_model=diagnosis.get("server_model"),
            category=diagnosis.get("category", "general"),
            confidence=diagnosis.get("confidence", 0) / 100.0,
            created_by=created_by,
            created_at=datetime.now(),
            tags=diagnosis.get("tags", []),
            sr_number=sr_number,
        )
        self.articles[article.id] = article
        self._persist(article)
        logger.info(f"KB article {article.id} created: {article.title}")
        return article

    def add_manual(self, title: str, root_cause: str, symptoms: List[str],
                   resolution: str, category: str, created_by: str,
                   tags: List[str] = None, server_model: str = None) -> KBArticle:
        article = KBArticle(
            id=str(uuid.uuid4())[:8], title=title, root_cause=root_cause,
            symptoms=symptoms, resolution=resolution, server_model=server_model,
            category=category, confidence=1.0, created_by=created_by,
            created_at=datetime.now(), tags=tags or [],
        )
        self.articles[article.id] = article
        self._persist(article)
        return article

    def search(self, query: str, category: str = None, limit: int = 10) -> List[Dict]:
        """Search KB by keyword match against title, root_cause, symptoms, tags."""
        q = query.lower()
        results = []
        for a in self.articles.values():
            score = 0
            if q in a.title.lower(): score += 3
            if q in a.root_cause.lower(): score += 2
            if any(q in s.lower() for s in a.symptoms): score += 1
            if any(q in t.lower() for t in a.tags): score += 1
            if category and a.category != category: continue
            if score > 0:
                a.views += 1
                results.append({"id": a.id, "title": a.title, "root_cause": a.root_cause,
                    "category": a.category, "confidence": a.confidence, "score": score,
                    "symptoms": a.symptoms[:3], "resolution": a.resolution[:200],
                    "server_model": a.server_model, "created_by": a.created_by,
                    "created_at": a.created_at.isoformat(), "views": a.views, "tags": a.tags})
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_article(self, article_id: str) -> Optional[Dict]:
        a = self.articles.get(article_id)
        if not a: return None
        a.views += 1
        return {"id": a.id, "title": a.title, "root_cause": a.root_cause,
            "symptoms": a.symptoms, "resolution": a.resolution,
            "category": a.category, "confidence": a.confidence,
            "server_model": a.server_model, "created_by": a.created_by,
            "created_at": a.created_at.isoformat(), "views": a.views,
            "tags": a.tags, "sr_number": a.sr_number}

    def _persist(self, article: KBArticle):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(self._file, 'a', encoding='utf-8') as f:
                f.write(json.dumps({"id": article.id, "title": article.title,
                    "root_cause": article.root_cause, "category": article.category,
                    "created_at": article.created_at.isoformat()}, default=str) + '\n')
        except Exception:
            pass

    def get_stats(self) -> Dict:
        by_cat = defaultdict(int)
        for a in self.articles.values():
            by_cat[a.category] += 1
        return {"total": len(self.articles), "by_category": dict(by_cat)}


# ═══════════════════════════════════════════════════════════════
#  #33 — INVESTIGATION SHARING
# ═══════════════════════════════════════════════════════════════

@dataclass
class SharedInvestigation:
    id: str
    investigation_data: Dict
    shared_by: str
    shared_with: List[str]  # usernames or "all"
    created_at: datetime
    notes: str = ""
    server_id: Optional[str] = None
    sr_number: Optional[str] = None

class InvestigationShareManager:
    """Share investigation results with other technicians."""

    def __init__(self):
        self.shares: Dict[str, SharedInvestigation] = {}

    def share(self, investigation_data: Dict, shared_by: str,
              shared_with: List[str] = None, notes: str = "",
              server_id: str = None, sr_number: str = None) -> SharedInvestigation:
        s = SharedInvestigation(
            id=str(uuid.uuid4())[:8], investigation_data=investigation_data,
            shared_by=shared_by, shared_with=shared_with or ["all"],
            created_at=datetime.now(), notes=notes,
            server_id=server_id, sr_number=sr_number,
        )
        self.shares[s.id] = s
        logger.info(f"Investigation {s.id} shared by {shared_by} with {shared_with or 'all'}")
        return s

    def get_shared_with_user(self, username: str) -> List[Dict]:
        result = []
        for s in sorted(self.shares.values(), key=lambda x: x.created_at, reverse=True):
            if "all" in s.shared_with or username in s.shared_with:
                result.append({
                    "id": s.id, "shared_by": s.shared_by, "notes": s.notes,
                    "server_id": s.server_id, "sr_number": s.sr_number,
                    "created_at": s.created_at.isoformat(),
                    "diagnosis_summary": s.investigation_data.get("diagnosis", {}).get("root_cause", "N/A"),
                    "confidence": s.investigation_data.get("diagnosis", {}).get("confidence", 0),
                })
        return result[:50]

    def get_full(self, share_id: str) -> Optional[Dict]:
        s = self.shares.get(share_id)
        if not s: return None
        return {"id": s.id, "investigation": s.investigation_data, "shared_by": s.shared_by,
                "notes": s.notes, "created_at": s.created_at.isoformat(),
                "server_id": s.server_id, "sr_number": s.sr_number}


# ═══════════════════════════════════════════════════════════════
#  #34 — EXTENDED METRIC HISTORY (file-backed)
# ═══════════════════════════════════════════════════════════════

class MetricHistoryStore:
    """File-backed metric history for long-term trending (days/weeks)."""

    def __init__(self, max_points: int = 100_000):
        self._file = os.path.join(_DATA_DIR, 'metric_history.jsonl')
        self.max_points = max_points
        self._buffer: List[Dict] = []
        self._flush_interval = 100  # flush every N points

    def record(self, server_id: str, metrics: Dict):
        """Record a metric snapshot for a server."""
        entry = {"ts": datetime.now().isoformat(), "server_id": server_id, "metrics": metrics}
        self._buffer.append(entry)
        if len(self._buffer) >= self._flush_interval:
            self._flush()

    def _flush(self):
        try:
            os.makedirs(_DATA_DIR, exist_ok=True)
            with open(self._file, 'a', encoding='utf-8') as f:
                for entry in self._buffer:
                    f.write(json.dumps(entry, default=str) + '\n')
            self._buffer.clear()
        except Exception as e:
            logger.warning(f"Metric history flush failed: {e}")

    def query(self, server_id: str = None, hours: int = 24, metric_name: str = None) -> List[Dict]:
        """Query stored metrics. Returns latest entries matching criteria."""
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        results = []
        try:
            if not os.path.exists(self._file):
                return results
            with open(self._file, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get('ts', '') < cutoff:
                            continue
                        if server_id and entry.get('server_id') != server_id:
                            continue
                        if metric_name:
                            val = entry.get('metrics', {}).get(metric_name)
                            if val is not None:
                                results.append({"ts": entry['ts'], "value": val})
                        else:
                            results.append(entry)
                    except json.JSONDecodeError:
                        pass
        except Exception:
            pass
        return results[-5000:]  # cap at 5000 points

    def get_stats(self) -> Dict:
        count = 0
        try:
            if os.path.exists(self._file):
                with open(self._file, 'r') as f:
                    count = sum(1 for _ in f)
        except Exception:
            pass
        return {"stored_points": count, "buffer_size": len(self._buffer)}


# ═══════════════════════════════════════════════════════════════
#  #35 — PER-SERVER / GROUP CUSTOM ALERT THRESHOLDS
# ═══════════════════════════════════════════════════════════════

class CustomThresholdManager:
    """Override global alert thresholds per server or group."""

    def __init__(self):
        # server_id or group_name -> metric_name -> {warning, critical}
        self.overrides: Dict[str, Dict[str, Dict[str, float]]] = {}

    def set_threshold(self, scope: str, metric: str, warning: float = None, critical: float = None):
        """Set custom threshold. scope = server_id or group name."""
        if scope not in self.overrides:
            self.overrides[scope] = {}
        self.overrides[scope][metric] = {}
        if warning is not None: self.overrides[scope][metric]["warning"] = warning
        if critical is not None: self.overrides[scope][metric]["critical"] = critical

    def get_threshold(self, server_id: str, metric: str, groups: List[str] = None,
                      default_warning: float = None, default_critical: float = None) -> Dict[str, float]:
        """Get effective threshold for a server/metric (server override > group > global)."""
        # Check server-specific override first
        if server_id in self.overrides and metric in self.overrides[server_id]:
            return self.overrides[server_id][metric]
        # Check group overrides
        for g in (groups or []):
            if g in self.overrides and metric in self.overrides[g]:
                return self.overrides[g][metric]
        # Fall back to defaults
        result = {}
        if default_warning is not None: result["warning"] = default_warning
        if default_critical is not None: result["critical"] = default_critical
        return result

    def list_overrides(self, scope: str = None) -> Dict:
        if scope:
            return self.overrides.get(scope, {})
        return dict(self.overrides)

    def delete_threshold(self, scope: str, metric: str = None):
        if scope in self.overrides:
            if metric:
                self.overrides[scope].pop(metric, None)
            else:
                del self.overrides[scope]


# ═══════════════════════════════════════════════════════════════
#  #36 — PAGERDUTY / SERVICENOW INCIDENT CREATION
# ═══════════════════════════════════════════════════════════════

class IncidentManager:
    """Create incidents in PagerDuty, ServiceNow, or custom webhook."""

    def __init__(self):
        self.config: Dict[str, str] = {}
        self.incidents: List[Dict] = []

    def configure(self, provider: str, api_url: str, api_key: str, **kwargs):
        self.config = {"provider": provider, "api_url": api_url, "api_key": api_key, **kwargs}
        logger.info(f"Incident manager configured: {provider}")

    def create_incident(self, title: str, description: str, severity: str,
                        server_id: str = None, created_by: str = None) -> Dict:
        """Create an incident record. In production, this would POST to PagerDuty/ServiceNow."""
        incident = {
            "id": str(uuid.uuid4())[:8],
            "title": title, "description": description,
            "severity": severity, "server_id": server_id,
            "created_by": created_by, "status": "open",
            "created_at": datetime.now().isoformat(),
            "provider": self.config.get("provider", "local"),
            # In production: POST to self.config["api_url"] with API key
            "external_id": None,  # Would be set by PagerDuty/ServiceNow response
        }
        self.incidents.append(incident)
        logger.info(f"Incident {incident['id']} created: {title} (severity: {severity})")
        return incident

    def list_incidents(self, status: str = None) -> List[Dict]:
        if status:
            return [i for i in self.incidents if i["status"] == status]
        return list(self.incidents)

    def resolve_incident(self, incident_id: str, resolved_by: str):
        for i in self.incidents:
            if i["id"] == incident_id:
                i["status"] = "resolved"
                i["resolved_by"] = resolved_by
                i["resolved_at"] = datetime.now().isoformat()
                return i
        raise ValueError(f"Incident {incident_id} not found")


# ═══════════════════════════════════════════════════════════════
#  #37 — SLA TRACKING
# ═══════════════════════════════════════════════════════════════

class SLATracker:
    """Track uptime %, MTTR, incident frequency per server."""

    def __init__(self):
        # server_id -> list of {start, end, type} events
        self.downtime_events: Dict[str, List[Dict]] = defaultdict(list)
        self.incident_events: Dict[str, List[Dict]] = defaultdict(list)

    def record_downtime(self, server_id: str, start: datetime, end: datetime = None, reason: str = ""):
        self.downtime_events[server_id].append({
            "start": start.isoformat(), "end": (end or datetime.now()).isoformat(), "reason": reason})

    def record_incident(self, server_id: str, severity: str, response_time_sec: float = 0,
                        resolution_time_sec: float = 0):
        self.incident_events[server_id].append({
            "ts": datetime.now().isoformat(), "severity": severity,
            "response_time_sec": response_time_sec, "resolution_time_sec": resolution_time_sec})

    def get_sla_report(self, server_id: str, days: int = 30) -> Dict:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        # Uptime calculation
        total_minutes = days * 24 * 60
        downtime_minutes = 0
        for evt in self.downtime_events.get(server_id, []):
            if evt["end"] >= cutoff:
                start = datetime.fromisoformat(evt["start"])
                end = datetime.fromisoformat(evt["end"])
                downtime_minutes += (end - start).total_seconds() / 60
        uptime_pct = max(0, ((total_minutes - downtime_minutes) / total_minutes) * 100) if total_minutes > 0 else 100
        # MTTR
        incidents = [e for e in self.incident_events.get(server_id, []) if e["ts"] >= cutoff]
        resolution_times = [e["resolution_time_sec"] for e in incidents if e["resolution_time_sec"] > 0]
        mttr_seconds = sum(resolution_times) / len(resolution_times) if resolution_times else 0
        return {
            "server_id": server_id, "period_days": days,
            "uptime_percent": round(uptime_pct, 3),
            "downtime_minutes": round(downtime_minutes, 1),
            "total_incidents": len(incidents),
            "mttr_seconds": round(mttr_seconds, 1),
            "mttr_human": f"{int(mttr_seconds // 60)}m {int(mttr_seconds % 60)}s" if mttr_seconds > 0 else "N/A",
            "incidents_by_severity": {s: sum(1 for e in incidents if e["severity"] == s)
                                     for s in ("critical", "high", "medium", "low")},
        }

    def get_fleet_sla(self, server_ids: List[str], days: int = 30) -> Dict:
        reports = [self.get_sla_report(sid, days) for sid in server_ids]
        if not reports:
            return {"avg_uptime": 100, "avg_mttr": 0, "total_incidents": 0, "servers": 0}
        avg_uptime = sum(r["uptime_percent"] for r in reports) / len(reports)
        avg_mttr = sum(r["mttr_seconds"] for r in reports) / len(reports)
        total_incidents = sum(r["total_incidents"] for r in reports)
        return {"avg_uptime": round(avg_uptime, 3), "avg_mttr_seconds": round(avg_mttr, 1),
                "total_incidents": total_incidents, "servers": len(reports), "per_server": reports}


# ═══════════════════════════════════════════════════════════════
#  #38 — GUIDED ONBOARDING
# ═══════════════════════════════════════════════════════════════

ONBOARDING_STEPS = [
    {"id": "welcome", "title": "Welcome to Medi-AI-tor", "description": "AI-powered Dell server diagnostics and management", "action": "read"},
    {"id": "connect", "title": "Connect to Your First Server", "description": "Enter iDRAC credentials in the connection panel to connect", "action": "connect_server"},
    {"id": "health_check", "title": "Run a Health Check", "description": "Click the Health Check button to see server status", "action": "click_health_check"},
    {"id": "explore_tabs", "title": "Explore System Info", "description": "Check the System Info tab to see CPU, memory, storage, firmware", "action": "click_system_tab"},
    {"id": "investigate", "title": "Try AI Investigation", "description": "Go to AI Investigation, describe an issue, and watch the agent diagnose it", "action": "start_investigation"},
    {"id": "chat", "title": "Chat with the Agent", "description": "Open the AI chat panel (bottom right) and ask any question", "action": "open_chat"},
    {"id": "operations", "title": "Explore Operations", "description": "Browse BIOS, RAID, Power, and Firmware operations available", "action": "click_operations_tab"},
    {"id": "fleet", "title": "Fleet Management", "description": "Visit the Fleet page to manage multiple servers", "action": "visit_fleet"},
    {"id": "monitoring", "title": "Real-time Monitoring", "description": "Visit the Monitoring page for live metrics and charts", "action": "visit_monitoring"},
    {"id": "complete", "title": "You're Ready!", "description": "You've completed onboarding. Explore the rest at your own pace!", "action": "complete"},
]

class OnboardingManager:
    """Track onboarding progress per user."""

    def __init__(self):
        self.progress: Dict[str, Dict] = {}  # username -> {completed_steps, current_step}

    def get_progress(self, username: str) -> Dict:
        if username not in self.progress:
            self.progress[username] = {"completed_steps": [], "current_step": 0, "completed": False}
        p = self.progress[username]
        return {
            "steps": ONBOARDING_STEPS,
            "completed_steps": p["completed_steps"],
            "current_step": p["current_step"],
            "total_steps": len(ONBOARDING_STEPS),
            "completed": p["completed"],
            "percent": int(len(p["completed_steps"]) / len(ONBOARDING_STEPS) * 100),
        }

    def complete_step(self, username: str, step_id: str) -> Dict:
        if username not in self.progress:
            self.progress[username] = {"completed_steps": [], "current_step": 0, "completed": False}
        p = self.progress[username]
        if step_id not in p["completed_steps"]:
            p["completed_steps"].append(step_id)
        # Advance current step
        step_ids = [s["id"] for s in ONBOARDING_STEPS]
        if step_id in step_ids:
            idx = step_ids.index(step_id)
            if idx >= p["current_step"]:
                p["current_step"] = min(idx + 1, len(ONBOARDING_STEPS) - 1)
        p["completed"] = len(p["completed_steps"]) >= len(ONBOARDING_STEPS) - 1
        return self.get_progress(username)

    def reset(self, username: str):
        self.progress.pop(username, None)


# ═══════════════════════════════════════════════════════════════
#  #39 — IN-APP GLOSSARY / DOCUMENTATION
# ═══════════════════════════════════════════════════════════════

GLOSSARY = {
    "iDRAC": {"term": "iDRAC", "definition": "Integrated Dell Remote Access Controller — an out-of-band management interface built into every Dell PowerEdge server. Allows remote monitoring, configuration, and power control even when the OS is offline.", "category": "hardware"},
    "Redfish": {"term": "Redfish", "definition": "An industry-standard RESTful API for server management defined by DMTF. iDRAC exposes a Redfish endpoint at https://<idrac-ip>/redfish/v1. Medi-AI-tor uses this API for all server interactions.", "category": "protocol"},
    "RACADM": {"term": "RACADM", "definition": "Remote Access Controller Admin — Dell's command-line utility for managing iDRAC. Used as a fallback when Redfish doesn't support certain operations.", "category": "tool"},
    "SEL": {"term": "SEL", "definition": "System Event Log — a hardware-level log stored in the BMC (iDRAC). Records hardware events, errors, and status changes. Critical for post-mortem analysis.", "category": "logs"},
    "TSR": {"term": "TSR", "definition": "Tech Support Report — a comprehensive diagnostic bundle collected from iDRAC containing SEL, LC logs, hardware inventory, configuration, and diagnostic results. Required by Dell Support for case escalation.", "category": "support"},
    "PERC": {"term": "PERC", "definition": "PowerEdge RAID Controller — Dell's hardware RAID controller. Manages virtual disks, RAID levels (0/1/5/6/10/50/60), hot spares, and drive rebuilds.", "category": "hardware"},
    "LC": {"term": "LC", "definition": "Lifecycle Controller — firmware in iDRAC that manages server deployment, updates, configuration, and diagnostics. Stores firmware packages and configuration profiles.", "category": "firmware"},
    "SCP": {"term": "SCP", "definition": "Server Configuration Profile — an XML/JSON export of all server settings (BIOS, iDRAC, RAID, NIC). Used for backup/restore and fleet-wide configuration deployment.", "category": "config"},
    "MCA": {"term": "MCA", "definition": "Machine Check Architecture — Intel/AMD CPU error reporting mechanism. MCA banks store hardware error codes that identify CPU, memory controller, cache, and bus errors.", "category": "errors"},
    "PCIe AER": {"term": "PCIe AER", "definition": "Advanced Error Reporting — PCI Express error detection and logging. Reports correctable and uncorrectable errors on PCIe devices (NICs, RAID controllers, GPUs).", "category": "errors"},
    "ECC": {"term": "ECC", "definition": "Error-Correcting Code — memory technology that detects and corrects single-bit errors. Correctable ECC errors are logged; uncorrectable errors (UCE) cause system crashes.", "category": "memory"},
    "DIMM": {"term": "DIMM", "definition": "Dual Inline Memory Module — a memory stick installed in the server. PowerEdge servers have 16-32 DIMM slots. Failed DIMMs show ECC errors in the SEL.", "category": "memory"},
    "PPR": {"term": "PPR", "definition": "Post Package Repair — a memory self-repair feature that maps out failed memory cells on DIMMs. Can be enabled in BIOS settings.", "category": "memory"},
    "NMI": {"term": "NMI", "definition": "Non-Maskable Interrupt — a hardware interrupt that cannot be ignored by the CPU. Used to force a memory dump (crash dump) for debugging blue screens or system hangs.", "category": "diagnostics"},
    "POST": {"term": "POST", "definition": "Power-On Self Test — the hardware initialization sequence that runs when a server boots. POST codes are displayed on the front panel LCD and logged in the SEL.", "category": "boot"},
    "BMC": {"term": "BMC", "definition": "Baseboard Management Controller — the embedded processor that runs iDRAC. Has its own network connection, memory, and firmware independent of the main server.", "category": "hardware"},
    "PSU": {"term": "PSU", "definition": "Power Supply Unit — converts AC power to DC for the server. PowerEdge servers typically have redundant PSUs (2 units) so one can fail without downtime.", "category": "power"},
    "C-States": {"term": "C-States", "definition": "CPU idle power states (C0=active, C1=halt, C3=sleep, C6=deep sleep). Disabling C-States reduces latency variability but increases power consumption.", "category": "performance"},
    "SR-IOV": {"term": "SR-IOV", "definition": "Single Root I/O Virtualization — allows a single PCIe device (like a NIC) to appear as multiple virtual devices. Required for efficient VM network passthrough.", "category": "virtualization"},
    "VT-x/VT-d": {"term": "VT-x/VT-d", "definition": "Intel Virtualization Technology. VT-x enables CPU virtualization; VT-d enables direct I/O device assignment to VMs (IOMMU). Both required for hypervisors.", "category": "virtualization"},
}

def search_glossary(query: str) -> List[Dict]:
    q = query.lower()
    results = []
    for entry in GLOSSARY.values():
        if q in entry["term"].lower() or q in entry["definition"].lower():
            results.append(entry)
    return results


# ═══════════════════════════════════════════════════════════════
#  #40 — INVESTIGATION REPORT EXPORT (HTML)
# ═══════════════════════════════════════════════════════════════

def generate_investigation_html(investigation: Dict, server_info: Dict = None) -> str:
    """Generate a self-contained HTML report from an investigation result."""
    diag = investigation.get("diagnosis", {})
    chain = investigation.get("reasoning_chain", [])
    recs = investigation.get("recommendations", [])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Investigation Report — Medi-AI-tor</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 40px auto; padding: 0 20px; color: #1e293b; line-height: 1.6; }}
h1 {{ color: #4f46e5; font-size: 1.5rem; border-bottom: 2px solid #4f46e5; padding-bottom: 8px; }}
h2 {{ color: #334155; font-size: 1.1rem; margin-top: 24px; }}
.badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 600; }}
.badge-crit {{ background: #fef2f2; color: #dc2626; }} .badge-warn {{ background: #fefce8; color: #a16207; }}
.badge-ok {{ background: #f0fdf4; color: #16a34a; }} .badge-info {{ background: #eff6ff; color: #2563eb; }}
table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.9rem; }}
th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
th {{ background: #f8fafc; font-weight: 600; color: #475569; font-size: 0.8rem; text-transform: uppercase; }}
.meta {{ color: #64748b; font-size: 0.85rem; }}
.finding {{ padding: 6px 12px; margin: 4px 0; border-radius: 6px; font-size: 0.88rem; }}
.finding-crit {{ background: #fef2f2; border-left: 3px solid #dc2626; }}
.finding-warn {{ background: #fefce8; border-left: 3px solid #f59e0b; }}
ol {{ padding-left: 20px; }} li {{ margin: 4px 0; font-size: 0.9rem; }}
.footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 0.75rem; }}
</style>
</head>
<body>
<h1>Medi-AI-tor Investigation Report</h1>
<p class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
"""
    if server_info:
        html += f"""<h2>Server</h2>
<table><tr><th>Model</th><td>{server_info.get('model','N/A')}</td><th>Service Tag</th><td>{server_info.get('service_tag','N/A')}</td></tr>
<tr><th>Host</th><td>{server_info.get('host','N/A')}</td><th>BIOS</th><td>{server_info.get('bios_version','N/A')}</td></tr></table>
"""
    # Diagnosis
    conf = diag.get('confidence', 0)
    conf_cls = 'ok' if conf >= 70 else 'warn' if conf >= 40 else 'crit'
    html += f"""<h2>Diagnosis</h2>
<p><strong>{diag.get('root_cause', 'No root cause identified')}</strong></p>
<p><span class="badge badge-{conf_cls}">{conf}% confidence</span> <span class="badge badge-info">{diag.get('category','N/A')}</span></p>
"""
    # Findings
    crits = diag.get('critical_findings', [])
    warns = diag.get('warning_findings', [])
    if crits or warns:
        html += "<h2>Findings</h2>"
        for f in crits:
            html += f'<div class="finding finding-crit">{f.get("description", f.get("message", str(f)))}</div>'
        for f in warns:
            html += f'<div class="finding finding-warn">{f.get("description", f.get("message", str(f)))}</div>'
    # Reasoning
    if chain:
        html += "<h2>Reasoning Chain</h2><ol>"
        for step in chain[:10]:
            html += f'<li>{step.get("reasoning", step.get("text", str(step)))}</li>'
        html += "</ol>"
    # Recommendations
    if recs:
        html += "<h2>Recommendations</h2><ol>"
        for r in recs[:10]:
            if isinstance(r, dict):
                html += f'<li><strong>{r.get("action","")}</strong>: {r.get("description","")}</li>'
            else:
                html += f'<li>{r}</li>'
        html += "</ol>"
    html += f'<div class="footer">Generated by Medi-AI-tor v2.0 | Dell Hackathon 2026</div></body></html>'
    return html


# ═══════════════════════════════════════════════════════════════
#  SINGLETON INSTANCES
# ═══════════════════════════════════════════════════════════════

shift_handoff_manager = ShiftHandoffManager()
knowledge_base_manager = KnowledgeBaseManager()
investigation_share_manager = InvestigationShareManager()
metric_history_store = MetricHistoryStore()
custom_threshold_manager = CustomThresholdManager()
incident_manager = IncidentManager()
sla_tracker = SLATracker()
onboarding_manager = OnboardingManager()
