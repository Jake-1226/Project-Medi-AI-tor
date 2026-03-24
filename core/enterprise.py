"""
Enterprise Features Module — Medi-AI-tor
Addresses enterprise adoption gaps #21-#30:
  #21 Per-server permissions
  #22 Custom roles
  #23 Role-based UI gating
  #24 Bulk CSV import
  #25 Maintenance window scheduling
  #26 Rolling firmware update orchestration
  #27 Rack/DC hierarchy
  #28 Ticketing integration
  #29 Server locking
  #30 Task assignment / work queue
"""

import logging
import csv
import io
import uuid
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#  #22 — CUSTOM ROLES WITH CONFIGURABLE PERMISSIONS
# ═══════════════════════════════════════════════════════════════

VALID_PERMISSIONS = {"read_only", "diagnostic", "full_control", "admin",
                     "webhook_manage", "user_manage", "system_config",
                     "fleet_manage", "bulk_operations"}

class CustomRoleManager:
    """Dynamic role management — create, update, delete roles at runtime."""

    def __init__(self):
        self.roles: Dict[str, Dict[str, Any]] = {
            "admin":      {"permissions": ["read_only", "diagnostic", "full_control", "admin", "user_manage", "fleet_manage", "bulk_operations"], "description": "Full system access", "builtin": True},
            "operator":   {"permissions": ["read_only", "diagnostic", "fleet_manage"], "description": "Diagnostics and fleet management", "builtin": True},
            "viewer":     {"permissions": ["read_only"], "description": "Read-only monitoring", "builtin": True},
            "technician": {"permissions": ["read_only", "diagnostic", "full_control", "fleet_manage"], "description": "Field technician with full server control", "builtin": True},
            "l1_support": {"permissions": ["read_only", "diagnostic"], "description": "Tier-1 support — diagnostics only, no destructive actions", "builtin": True},
        }

    def create_role(self, name: str, permissions: List[str], description: str = "") -> Dict:
        if name in self.roles:
            raise ValueError(f"Role '{name}' already exists")
        invalid = set(permissions) - VALID_PERMISSIONS
        if invalid:
            raise ValueError(f"Invalid permissions: {invalid}")
        self.roles[name] = {"permissions": permissions, "description": description, "builtin": False}
        logger.info(f"Custom role created: {name} with {permissions}")
        return self.roles[name]

    def update_role(self, name: str, permissions: List[str] = None, description: str = None) -> Dict:
        if name not in self.roles:
            raise ValueError(f"Role '{name}' not found")
        if self.roles[name].get("builtin"):
            raise ValueError(f"Cannot modify builtin role '{name}'")
        if permissions is not None:
            invalid = set(permissions) - VALID_PERMISSIONS
            if invalid:
                raise ValueError(f"Invalid permissions: {invalid}")
            self.roles[name]["permissions"] = permissions
        if description is not None:
            self.roles[name]["description"] = description
        return self.roles[name]

    def delete_role(self, name: str):
        if name not in self.roles:
            raise ValueError(f"Role '{name}' not found")
        if self.roles[name].get("builtin"):
            raise ValueError(f"Cannot delete builtin role '{name}'")
        del self.roles[name]

    def get_role(self, name: str) -> Optional[Dict]:
        return self.roles.get(name)

    def list_roles(self) -> Dict[str, Dict]:
        return dict(self.roles)

    def get_permissions_for_role(self, name: str) -> List[str]:
        role = self.roles.get(name)
        return role["permissions"] if role else []


# ═══════════════════════════════════════════════════════════════
#  #21 — PER-SERVER / GROUP PERMISSION SCOPING
# ═══════════════════════════════════════════════════════════════

class ServerPermissionManager:
    """Restrict user access to specific servers or server groups."""

    def __init__(self):
        # user -> set of server_ids they can access (empty = all)
        self.user_server_scope: Dict[str, Set[str]] = {}
        # user -> set of group names they can access (empty = all)
        self.user_group_scope: Dict[str, Set[str]] = {}

    def set_user_scope(self, username: str, server_ids: List[str] = None, group_names: List[str] = None):
        if server_ids is not None:
            self.user_server_scope[username] = set(server_ids)
        if group_names is not None:
            self.user_group_scope[username] = set(group_names)

    def clear_user_scope(self, username: str):
        self.user_server_scope.pop(username, None)
        self.user_group_scope.pop(username, None)

    def can_access_server(self, username: str, server_id: str, server_groups: Set[str] = None) -> bool:
        """Check if user can access a specific server."""
        # Admins always have access
        # If no scope set, user has access to everything
        if username not in self.user_server_scope and username not in self.user_group_scope:
            return True
        # Direct server access
        if username in self.user_server_scope:
            if server_id in self.user_server_scope[username]:
                return True
        # Group-based access
        if username in self.user_group_scope and server_groups:
            if self.user_group_scope[username] & server_groups:
                return True
        return False

    def filter_servers(self, username: str, servers: Dict[str, Any]) -> Dict[str, Any]:
        """Filter server dict to only those the user can access."""
        if username not in self.user_server_scope and username not in self.user_group_scope:
            return servers
        return {sid: s for sid, s in servers.items()
                if self.can_access_server(username, sid, getattr(s, 'groups', set()))}

    def get_user_scope(self, username: str) -> Dict:
        return {
            "server_ids": list(self.user_server_scope.get(username, [])),
            "group_names": list(self.user_group_scope.get(username, [])),
            "unrestricted": username not in self.user_server_scope and username not in self.user_group_scope,
        }


# ═══════════════════════════════════════════════════════════════
#  #23 — ROLE-BASED UI GATING
# ═══════════════════════════════════════════════════════════════

def get_ui_capabilities(role: str, permissions: List[str]) -> Dict[str, bool]:
    """Return a map of UI features the user's role can see/use.
    
    The frontend calls GET /api/auth/capabilities and uses this
    to show/hide buttons, tabs, and sections.
    """
    perms = set(permissions)
    return {
        # Tabs
        "tab_overview": True,
        "tab_system_info": True,
        "tab_health": True,
        "tab_logs": True,
        "tab_investigation": True,
        "tab_operations": "diagnostic" in perms or "full_control" in perms,
        "tab_advanced": "diagnostic" in perms or "full_control" in perms,
        # Quick actions
        "action_health_check": True,
        "action_refresh_data": True,
        "action_collect_logs": True,
        "action_performance": "diagnostic" in perms,
        # Power operations
        "action_shutdown": "full_control" in perms,
        "action_power_cycle": "full_control" in perms,
        "action_ac_power_cycle": "full_control" in perms,
        "action_reset_idrac": "full_control" in perms,
        # Operations sub-tabs
        "ops_bios": "diagnostic" in perms,
        "ops_raid": "full_control" in perms,
        "ops_drives": "full_control" in perms,
        "ops_power": "diagnostic" in perms,
        "ops_idrac": "full_control" in perms,
        "ops_firmware": "full_control" in perms,
        "ops_network": "diagnostic" in perms,
        "ops_os": "diagnostic" in perms,
        # Fleet
        "fleet_manage": "fleet_manage" in perms or "admin" in perms,
        "fleet_bulk_ops": "bulk_operations" in perms or "admin" in perms,
        "fleet_add_server": "fleet_manage" in perms or "admin" in perms,
        "fleet_delete_server": "admin" in perms,
        # Admin
        "admin_users": "user_manage" in perms or "admin" in perms,
        "admin_audit_log": "admin" in perms,
        "admin_webhooks": "webhook_manage" in perms or "admin" in perms,
    }


# ═══════════════════════════════════════════════════════════════
#  #24 — BULK CSV IMPORT
# ═══════════════════════════════════════════════════════════════

def parse_csv_import(csv_content: str) -> List[Dict[str, str]]:
    """Parse CSV content into a list of server dicts.
    
    Expected columns: name, host, username, password, port, environment, location, tags, notes
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    servers = []
    required = {"name", "host", "username", "password"}
    for i, row in enumerate(reader, start=2):
        row = {k.strip().lower(): v.strip() for k, v in row.items() if k}
        missing = required - set(row.keys())
        if missing:
            raise ValueError(f"Row {i}: missing required columns {missing}")
        if not row["host"] or not row["username"] or not row["password"]:
            raise ValueError(f"Row {i}: host, username, and password cannot be empty")
        servers.append({
            "name": row.get("name", row["host"]),
            "host": row["host"],
            "username": row["username"],
            "password": row["password"],
            "port": int(row.get("port", "443")),
            "environment": row.get("environment", ""),
            "location": row.get("location", ""),
            "datacenter": row.get("datacenter", ""),
            "rack": row.get("rack", ""),
            "tags": [t.strip() for t in row.get("tags", "").split(",") if t.strip()],
            "notes": row.get("notes", ""),
        })
    return servers


# ═══════════════════════════════════════════════════════════════
#  #25 — MAINTENANCE WINDOW SCHEDULING
# ═══════════════════════════════════════════════════════════════

@dataclass
class MaintenanceWindow:
    id: str
    server_ids: List[str]
    group_name: Optional[str]
    start_time: datetime
    end_time: datetime
    description: str
    created_by: str
    status: str = "scheduled"  # scheduled, active, completed, cancelled
    suppress_alerts: bool = True

class MaintenanceScheduler:
    """Schedule and manage maintenance windows for servers/groups."""

    def __init__(self):
        self.windows: Dict[str, MaintenanceWindow] = {}

    def schedule(self, server_ids: List[str], start: datetime, end: datetime,
                 description: str, created_by: str, group_name: str = None,
                 suppress_alerts: bool = True) -> MaintenanceWindow:
        if end <= start:
            raise ValueError("End time must be after start time")
        mw = MaintenanceWindow(
            id=str(uuid.uuid4())[:8],
            server_ids=server_ids,
            group_name=group_name,
            start_time=start,
            end_time=end,
            description=description,
            created_by=created_by,
            suppress_alerts=suppress_alerts,
        )
        self.windows[mw.id] = mw
        logger.info(f"Maintenance window {mw.id} scheduled: {description} ({start} - {end}) for {len(server_ids)} servers")
        return mw

    def cancel(self, window_id: str):
        if window_id not in self.windows:
            raise ValueError(f"Window {window_id} not found")
        self.windows[window_id].status = "cancelled"

    def get_active_windows(self) -> List[MaintenanceWindow]:
        now = datetime.now()
        active = []
        for mw in self.windows.values():
            if mw.status == "cancelled":
                continue
            if mw.start_time <= now <= mw.end_time:
                mw.status = "active"
                active.append(mw)
            elif now > mw.end_time and mw.status != "completed":
                mw.status = "completed"
        return active

    def is_server_in_maintenance(self, server_id: str) -> bool:
        return any(server_id in mw.server_ids for mw in self.get_active_windows())

    def list_windows(self, include_completed: bool = False) -> List[Dict]:
        result = []
        for mw in self.windows.values():
            if not include_completed and mw.status == "completed":
                continue
            result.append({
                "id": mw.id, "server_ids": mw.server_ids, "group_name": mw.group_name,
                "start_time": mw.start_time.isoformat(), "end_time": mw.end_time.isoformat(),
                "description": mw.description, "created_by": mw.created_by,
                "status": mw.status, "suppress_alerts": mw.suppress_alerts,
            })
        return result


# ═══════════════════════════════════════════════════════════════
#  #26 — ROLLING FIRMWARE UPDATE ORCHESTRATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class RollingUpdatePlan:
    id: str
    server_ids: List[str]
    batch_size: int
    firmware_component: str
    firmware_version: str
    created_by: str
    status: str = "planned"  # planned, in_progress, paused, completed, failed
    completed_servers: List[str] = field(default_factory=list)
    failed_servers: List[str] = field(default_factory=list)
    current_batch: int = 0
    health_gate: bool = True  # pause if health degrades after a batch

class RollingUpdateOrchestrator:
    """Orchestrate firmware updates across server groups in batches."""

    def __init__(self):
        self.plans: Dict[str, RollingUpdatePlan] = {}

    def create_plan(self, server_ids: List[str], component: str, version: str,
                    batch_size: int, created_by: str, health_gate: bool = True) -> RollingUpdatePlan:
        plan = RollingUpdatePlan(
            id=str(uuid.uuid4())[:8],
            server_ids=server_ids,
            batch_size=max(1, batch_size),
            firmware_component=component,
            firmware_version=version,
            created_by=created_by,
            health_gate=health_gate,
        )
        self.plans[plan.id] = plan
        logger.info(f"Rolling update plan {plan.id}: {component} -> {version}, {len(server_ids)} servers in batches of {batch_size}")
        return plan

    def get_next_batch(self, plan_id: str) -> List[str]:
        plan = self.plans.get(plan_id)
        if not plan:
            return []
        done = set(plan.completed_servers) | set(plan.failed_servers)
        remaining = [s for s in plan.server_ids if s not in done]
        return remaining[:plan.batch_size]

    def record_batch_result(self, plan_id: str, succeeded: List[str], failed: List[str]):
        plan = self.plans.get(plan_id)
        if not plan:
            return
        plan.completed_servers.extend(succeeded)
        plan.failed_servers.extend(failed)
        plan.current_batch += 1
        done = set(plan.completed_servers) | set(plan.failed_servers)
        if len(done) >= len(plan.server_ids):
            plan.status = "completed" if not plan.failed_servers else "completed_with_failures"
        elif plan.health_gate and failed:
            plan.status = "paused"
        else:
            plan.status = "in_progress"

    def get_plan_status(self, plan_id: str) -> Optional[Dict]:
        plan = self.plans.get(plan_id)
        if not plan:
            return None
        return {
            "id": plan.id, "status": plan.status, "component": plan.firmware_component,
            "version": plan.firmware_version, "total": len(plan.server_ids),
            "completed": len(plan.completed_servers), "failed": len(plan.failed_servers),
            "current_batch": plan.current_batch, "batch_size": plan.batch_size,
            "health_gate": plan.health_gate,
        }

    def list_plans(self) -> List[Dict]:
        return [self.get_plan_status(pid) for pid in self.plans]


# ═══════════════════════════════════════════════════════════════
#  #27 — RACK / DATA CENTER HIERARCHY
# ═══════════════════════════════════════════════════════════════

@dataclass
class LocationHierarchy:
    datacenter: str = ""
    room: str = ""
    rack: str = ""
    rack_unit: str = ""

    def to_dict(self) -> Dict:
        return {"datacenter": self.datacenter, "room": self.room,
                "rack": self.rack, "rack_unit": self.rack_unit}

    def matches_filter(self, dc: str = None, rack: str = None) -> bool:
        if dc and self.datacenter.lower() != dc.lower():
            return False
        if rack and self.rack.lower() != rack.lower():
            return False
        return True


# ═══════════════════════════════════════════════════════════════
#  #28 — TICKETING INTEGRATION (ServiceNow / Jira webhook)
# ═══════════════════════════════════════════════════════════════

class TicketingIntegration:
    """Webhook-based integration with ServiceNow, Jira, or any ticket system."""

    def __init__(self):
        self.config: Dict[str, str] = {
            "provider": "",       # "servicenow", "jira", "webhook"
            "base_url": "",       # e.g. https://instance.service-now.com
            "api_token": "",
            "project_key": "",    # Jira project key
            "assignment_group": "",  # ServiceNow assignment group
        }
        self.tickets: Dict[str, Dict] = {}  # sr_number -> ticket info

    def configure(self, provider: str, base_url: str, api_token: str, **kwargs):
        self.config.update(provider=provider, base_url=base_url, api_token=api_token, **kwargs)
        logger.info(f"Ticketing integration configured: {provider} at {base_url}")

    def link_ticket(self, sr_number: str, server_id: str, investigation_id: str = None,
                    summary: str = "", priority: str = "medium") -> Dict:
        ticket = {
            "sr_number": sr_number, "server_id": server_id,
            "investigation_id": investigation_id, "summary": summary,
            "priority": priority, "status": "open",
            "created_at": datetime.now().isoformat(),
            "provider": self.config.get("provider", "manual"),
        }
        self.tickets[sr_number] = ticket
        logger.info(f"Ticket {sr_number} linked to server {server_id}")
        return ticket

    def update_ticket_status(self, sr_number: str, status: str, notes: str = ""):
        if sr_number in self.tickets:
            self.tickets[sr_number]["status"] = status
            if notes:
                self.tickets[sr_number].setdefault("notes", []).append(
                    {"text": notes, "ts": datetime.now().isoformat()})

    def get_tickets_for_server(self, server_id: str) -> List[Dict]:
        return [t for t in self.tickets.values() if t["server_id"] == server_id]

    def list_open_tickets(self) -> List[Dict]:
        return [t for t in self.tickets.values() if t["status"] in ("open", "in_progress")]

    def get_config(self) -> Dict:
        safe = dict(self.config)
        if safe.get("api_token"):
            safe["api_token"] = "***" + safe["api_token"][-4:] if len(safe["api_token"]) > 4 else "***"
        return safe


# ═══════════════════════════════════════════════════════════════
#  #29 — SERVER LOCKING FOR CONCURRENT ACCESS
# ═══════════════════════════════════════════════════════════════

@dataclass
class ServerLock:
    server_id: str
    locked_by: str
    locked_at: datetime
    reason: str = ""
    expires_at: Optional[datetime] = None

class ServerLockManager:
    """Prevent concurrent modifications to the same server."""

    def __init__(self, default_ttl_minutes: int = 30):
        self.locks: Dict[str, ServerLock] = {}
        self.default_ttl = timedelta(minutes=default_ttl_minutes)

    def acquire(self, server_id: str, username: str, reason: str = "", ttl_minutes: int = None) -> ServerLock:
        self._cleanup_expired()
        if server_id in self.locks:
            existing = self.locks[server_id]
            if existing.locked_by != username:
                raise ValueError(f"Server {server_id} is locked by {existing.locked_by} since {existing.locked_at.isoformat()} — {existing.reason}")
        ttl = timedelta(minutes=ttl_minutes) if ttl_minutes else self.default_ttl
        lock = ServerLock(
            server_id=server_id, locked_by=username,
            locked_at=datetime.now(), reason=reason,
            expires_at=datetime.now() + ttl,
        )
        self.locks[server_id] = lock
        logger.info(f"Server {server_id} locked by {username}: {reason}")
        return lock

    def release(self, server_id: str, username: str):
        if server_id in self.locks:
            if self.locks[server_id].locked_by != username:
                raise ValueError(f"Cannot release lock owned by {self.locks[server_id].locked_by}")
            del self.locks[server_id]

    def is_locked(self, server_id: str) -> Optional[Dict]:
        self._cleanup_expired()
        lock = self.locks.get(server_id)
        if not lock:
            return None
        return {"locked_by": lock.locked_by, "locked_at": lock.locked_at.isoformat(),
                "reason": lock.reason, "expires_at": lock.expires_at.isoformat() if lock.expires_at else None}

    def get_user_locks(self, username: str) -> List[Dict]:
        self._cleanup_expired()
        return [{"server_id": l.server_id, "reason": l.reason, "locked_at": l.locked_at.isoformat()}
                for l in self.locks.values() if l.locked_by == username]

    def _cleanup_expired(self):
        now = datetime.now()
        expired = [sid for sid, lock in self.locks.items() if lock.expires_at and now > lock.expires_at]
        for sid in expired:
            logger.info(f"Lock expired for server {sid} (was held by {self.locks[sid].locked_by})")
            del self.locks[sid]


# ═══════════════════════════════════════════════════════════════
#  #30 — TASK ASSIGNMENT / WORK QUEUE
# ═══════════════════════════════════════════════════════════════

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class Task:
    id: str
    title: str
    description: str
    server_id: Optional[str]
    assigned_to: Optional[str]
    created_by: str
    priority: str
    status: str = "open"  # open, in_progress, completed, cancelled
    created_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    sr_number: Optional[str] = None
    investigation_id: Optional[str] = None

class TaskManager:
    """Work queue for assigning investigations and tasks to technicians."""

    def __init__(self):
        self.tasks: Dict[str, Task] = {}

    def create_task(self, title: str, description: str, created_by: str,
                    server_id: str = None, assigned_to: str = None,
                    priority: str = "medium", sr_number: str = None) -> Task:
        task = Task(
            id=str(uuid.uuid4())[:8], title=title, description=description,
            server_id=server_id, assigned_to=assigned_to, created_by=created_by,
            priority=priority, sr_number=sr_number,
        )
        self.tasks[task.id] = task
        logger.info(f"Task {task.id} created: {title} (assigned to {assigned_to or 'unassigned'})")
        return task

    def assign(self, task_id: str, username: str):
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.assigned_to = username
        task.status = "in_progress"

    def complete(self, task_id: str):
        task = self.tasks.get(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        task.status = "completed"
        task.completed_at = datetime.now()

    def get_queue(self, assigned_to: str = None, status: str = None) -> List[Dict]:
        result = []
        for task in sorted(self.tasks.values(), key=lambda t: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(t.priority, 2), t.created_at)):
            if assigned_to and task.assigned_to != assigned_to:
                continue
            if status and task.status != status:
                continue
            result.append({
                "id": task.id, "title": task.title, "description": task.description,
                "server_id": task.server_id, "assigned_to": task.assigned_to,
                "created_by": task.created_by, "priority": task.priority,
                "status": task.status, "sr_number": task.sr_number,
                "created_at": task.created_at.isoformat(),
                "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            })
        return result

    def get_stats(self) -> Dict:
        total = len(self.tasks)
        by_status = {}
        by_assignee = {}
        for t in self.tasks.values():
            by_status[t.status] = by_status.get(t.status, 0) + 1
            if t.assigned_to:
                by_assignee[t.assigned_to] = by_assignee.get(t.assigned_to, 0) + 1
        return {"total": total, "by_status": by_status, "by_assignee": by_assignee}


# ═══════════════════════════════════════════════════════════════
#  SINGLETON INSTANCES
# ═══════════════════════════════════════════════════════════════

custom_role_manager = CustomRoleManager()
server_permission_manager = ServerPermissionManager()
maintenance_scheduler = MaintenanceScheduler()
rolling_update_orchestrator = RollingUpdateOrchestrator()
ticketing_integration = TicketingIntegration()
server_lock_manager = ServerLockManager()
task_manager = TaskManager()
