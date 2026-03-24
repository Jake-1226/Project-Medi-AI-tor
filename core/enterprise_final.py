"""
Enterprise Final Features — Medi-AI-tor
Addresses remaining enterprise gaps #41-#67
"""
import logging, json, os, uuid, time, csv, io, re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)) or '.', 'data')

# ═══════════════════════════════════════════════════════════════
#  #41 — TRAINABLE AI: Custom runbooks + org-specific hypotheses
# ═══════════════════════════════════════════════════════════════

class CustomRunbookManager:
    """Allow organizations to add custom runbooks and hypotheses the AI can use."""
    def __init__(self):
        self.runbooks: Dict[str, Dict] = {}
        self.custom_hypotheses: List[Dict] = []

    def add_runbook(self, title: str, symptoms: List[str], steps: List[str],
                    category: str, created_by: str, priority: int = 5) -> Dict:
        rb = {"id": str(uuid.uuid4())[:8], "title": title, "symptoms": symptoms,
              "steps": steps, "category": category, "created_by": created_by,
              "priority": priority, "created_at": datetime.now().isoformat(), "usage_count": 0}
        self.runbooks[rb["id"]] = rb
        return rb

    def add_hypothesis(self, description: str, category: str, keywords: List[str],
                       initial_confidence: float = 0.3, created_by: str = "") -> Dict:
        h = {"id": str(uuid.uuid4())[:8], "description": description, "category": category,
             "keywords": keywords, "initial_confidence": initial_confidence,
             "created_by": created_by, "created_at": datetime.now().isoformat()}
        self.custom_hypotheses.append(h)
        return h

    def match_runbooks(self, issue_text: str) -> List[Dict]:
        issue = issue_text.lower()
        matches = []
        for rb in self.runbooks.values():
            score = sum(1 for s in rb["symptoms"] if s.lower() in issue)
            if score > 0:
                rb["usage_count"] += 1
                matches.append({**rb, "match_score": score})
        matches.sort(key=lambda x: (-x["match_score"], -x["priority"]))
        return matches[:5]

    def list_all(self) -> Dict:
        return {"runbooks": list(self.runbooks.values()), "custom_hypotheses": self.custom_hypotheses}


# ═══════════════════════════════════════════════════════════════
#  #42 — FALSE POSITIVE TRACKING / FEEDBACK LOOP
# ═══════════════════════════════════════════════════════════════

class InvestigationFeedbackManager:
    """Track accuracy of investigations; enable learning from feedback."""
    def __init__(self):
        self.feedback: List[Dict] = []

    def submit(self, investigation_id: str, was_correct: bool, actual_cause: str = "",
               notes: str = "", submitted_by: str = "") -> Dict:
        fb = {"id": str(uuid.uuid4())[:8], "investigation_id": investigation_id,
              "was_correct": was_correct, "actual_cause": actual_cause, "notes": notes,
              "submitted_by": submitted_by, "submitted_at": datetime.now().isoformat()}
        self.feedback.append(fb)
        return fb

    def get_accuracy_stats(self) -> Dict:
        if not self.feedback:
            return {"total": 0, "correct": 0, "incorrect": 0, "accuracy_pct": 0}
        correct = sum(1 for f in self.feedback if f["was_correct"])
        return {"total": len(self.feedback), "correct": correct,
                "incorrect": len(self.feedback) - correct,
                "accuracy_pct": round(correct / len(self.feedback) * 100, 1)}

    def list_feedback(self, limit: int = 50) -> List[Dict]:
        return self.feedback[-limit:]


# ═══════════════════════════════════════════════════════════════
#  #43 — MULTI-VENDOR SERVER SUPPORT ABSTRACTION
# ═══════════════════════════════════════════════════════════════

SUPPORTED_VENDORS = {
    "dell": {"name": "Dell PowerEdge", "protocol": "Redfish", "status": "full", "models": ["PowerEdge R750", "PowerEdge R650", "PowerScale F710"]},
    "hpe": {"name": "HPE ProLiant", "protocol": "Redfish (iLO)", "status": "planned", "models": ["ProLiant DL380", "ProLiant DL360"]},
    "lenovo": {"name": "Lenovo ThinkSystem", "protocol": "Redfish (XCC)", "status": "planned", "models": ["ThinkSystem SR650", "ThinkSystem SR630"]},
    "cisco": {"name": "Cisco UCS", "protocol": "Redfish (CIMC)", "status": "planned", "models": ["UCS C220", "UCS C240"]},
    "supermicro": {"name": "Supermicro", "protocol": "Redfish (BMC)", "status": "planned", "models": []},
}

def get_vendor_support() -> Dict:
    return {"vendors": SUPPORTED_VENDORS, "current": "dell", "note": "Multi-vendor via Redfish standard. HPE/Lenovo/Cisco planned for Phase 5."}


# ═══════════════════════════════════════════════════════════════
#  #44 — DASHBOARD CUSTOMIZATION (saved layouts per user)
# ═══════════════════════════════════════════════════════════════

class DashboardLayoutManager:
    """Save and restore per-user dashboard layouts and preferences."""
    def __init__(self):
        self.layouts: Dict[str, Dict] = {}  # username -> layout config

    def save_layout(self, username: str, layout: Dict) -> Dict:
        self.layouts[username] = {**layout, "updated_at": datetime.now().isoformat()}
        return self.layouts[username]

    def get_layout(self, username: str) -> Optional[Dict]:
        return self.layouts.get(username)

    def reset_layout(self, username: str):
        self.layouts.pop(username, None)


# ═══════════════════════════════════════════════════════════════
#  #46 — SERVER BOOKMARKS / FAVORITES
# ═══════════════════════════════════════════════════════════════

class BookmarkManager:
    """Per-user server bookmarks/favorites."""
    def __init__(self):
        self.bookmarks: Dict[str, List[str]] = {}  # username -> [server_ids]

    def add(self, username: str, server_id: str):
        if username not in self.bookmarks:
            self.bookmarks[username] = []
        if server_id not in self.bookmarks[username]:
            self.bookmarks[username].append(server_id)

    def remove(self, username: str, server_id: str):
        if username in self.bookmarks:
            self.bookmarks[username] = [s for s in self.bookmarks[username] if s != server_id]

    def get(self, username: str) -> List[str]:
        return self.bookmarks.get(username, [])


# ═══════════════════════════════════════════════════════════════
#  #50 — EXECUTIVE SUMMARY REPORTS + TECHNICIAN METRICS
# ═══════════════════════════════════════════════════════════════

class ExecutiveReportGenerator:
    """Generate executive summaries and per-technician productivity metrics."""
    def __init__(self):
        self.technician_actions: Dict[str, List[Dict]] = defaultdict(list)

    def record_action(self, username: str, action: str, server_id: str = None):
        self.technician_actions[username].append(
            {"action": action, "server_id": server_id, "ts": datetime.now().isoformat()})

    def get_technician_metrics(self, username: str = None, days: int = 30) -> Dict:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        if username:
            actions = [a for a in self.technician_actions.get(username, []) if a["ts"] >= cutoff]
            return {"username": username, "period_days": days, "total_actions": len(actions),
                    "actions_by_type": dict(defaultdict(int, {a["action"]: 1 for a in actions}))}
        all_metrics = {}
        for user, actions in self.technician_actions.items():
            filtered = [a for a in actions if a["ts"] >= cutoff]
            all_metrics[user] = {"total_actions": len(filtered)}
        return {"period_days": days, "technicians": all_metrics, "total_technicians": len(all_metrics)}

    def generate_executive_summary(self, fleet_overview: Dict, sla_data: Dict,
                                    incident_count: int, kb_count: int) -> Dict:
        return {
            "generated_at": datetime.now().isoformat(),
            "fleet": {"total_servers": fleet_overview.get("total", 0),
                      "online": fleet_overview.get("online", 0),
                      "health_avg": fleet_overview.get("avg_health", 0)},
            "sla": {"uptime_pct": sla_data.get("avg_uptime", 100),
                    "mttr_seconds": sla_data.get("avg_mttr_seconds", 0)},
            "operations": {"total_incidents": incident_count,
                           "kb_articles": kb_count,
                           "technician_metrics": self.get_technician_metrics()},
        }


# ═══════════════════════════════════════════════════════════════
#  #51 — BI TOOL DATA EXPORT (CSV/JSON API)
# ═══════════════════════════════════════════════════════════════

def export_for_bi(data: List[Dict], format: str = "csv") -> str:
    """Export data in CSV or JSON format for BI tools (Splunk, Tableau, PowerBI)."""
    if format == "json":
        return json.dumps(data, default=str, indent=2)
    if not data:
        return ""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=data[0].keys())
    writer.writeheader()
    for row in data:
        writer.writerow({k: str(v).replace('\n', ' ') for k, v in row.items()})
    return output.getvalue()


# ═══════════════════════════════════════════════════════════════
#  #64 — @MENTIONS / COMMENTS ON SERVERS
# ═══════════════════════════════════════════════════════════════

class CommentManager:
    """Comments and @mentions on servers/issues."""
    def __init__(self):
        self.comments: Dict[str, List[Dict]] = defaultdict(list)  # server_id -> comments

    def add_comment(self, server_id: str, text: str, author: str) -> Dict:
        mentions = re.findall(r'@(\w+)', text)
        comment = {"id": str(uuid.uuid4())[:8], "text": text, "author": author,
                   "mentions": mentions, "created_at": datetime.now().isoformat()}
        self.comments[server_id].append(comment)
        return comment

    def get_comments(self, server_id: str) -> List[Dict]:
        return self.comments.get(server_id, [])

    def get_mentions(self, username: str) -> List[Dict]:
        result = []
        for sid, comments in self.comments.items():
            for c in comments:
                if username in c.get("mentions", []):
                    result.append({**c, "server_id": sid})
        return sorted(result, key=lambda x: x["created_at"], reverse=True)[:50]


# ═══════════════════════════════════════════════════════════════
#  #65 — SERVER COMPARISON VIEW
# ═══════════════════════════════════════════════════════════════

def compare_servers(servers: List[Dict]) -> Dict:
    """Compare health/config across multiple servers."""
    if len(servers) < 2:
        return {"error": "Need at least 2 servers to compare"}
    fields = ["model", "environment", "health_score", "status", "alert_count",
              "datacenter", "rack", "tags"]
    comparison = {"servers": [], "differences": [], "common": {}}
    for s in servers:
        comparison["servers"].append({f: s.get(f) for f in ["id", "name"] + fields})
    # Find differences
    for f in fields:
        vals = [s.get(f) for s in servers]
        if len(set(str(v) for v in vals)) > 1:
            comparison["differences"].append({"field": f, "values": {s.get("name", s.get("id","?")): s.get(f) for s in servers}})
        elif vals:
            comparison["common"][f] = vals[0]
    return comparison


# ═══════════════════════════════════════════════════════════════
#  #66 — SAVED SEARCHES / FILTER PRESETS
# ═══════════════════════════════════════════════════════════════

class SavedSearchManager:
    """Per-user saved search filters for fleet view."""
    def __init__(self):
        self.searches: Dict[str, List[Dict]] = defaultdict(list)  # username -> saved searches

    def save(self, username: str, name: str, filters: Dict) -> Dict:
        search = {"id": str(uuid.uuid4())[:8], "name": name, "filters": filters,
                  "created_at": datetime.now().isoformat()}
        self.searches[username].append(search)
        return search

    def get(self, username: str) -> List[Dict]:
        return self.searches.get(username, [])

    def delete(self, username: str, search_id: str):
        self.searches[username] = [s for s in self.searches.get(username, []) if s["id"] != search_id]


# ═══════════════════════════════════════════════════════════════
#  SINGLETON INSTANCES
# ═══════════════════════════════════════════════════════════════

custom_runbook_manager = CustomRunbookManager()
investigation_feedback_manager = InvestigationFeedbackManager()
dashboard_layout_manager = DashboardLayoutManager()
bookmark_manager = BookmarkManager()
executive_report_generator = ExecutiveReportGenerator()
comment_manager = CommentManager()
saved_search_manager = SavedSearchManager()
