#!/usr/bin/env python3
"""
Medi-AI-tor — Dell Server AI Diagnostics Agent
A lightweight AI agent that acts as an intermediary between Virtual Assistants 
and Dell servers, leveraging Redfish API and RACADM for comprehensive server management.
"""

import asyncio
import logging
import os
import time
import re
from collections import defaultdict
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Union
from starlette.middleware.base import BaseHTTPMiddleware
import json
import uvicorn
from enum import Enum
from datetime import datetime, date
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from core.agent_core import DellAIAgent
from core.config import AgentConfig
from core.agent_brain import AgentBrain
from core.session_manager import SessionConnectionManager
from core.automation_engine import AutomationEngine
from core.multi_server_manager import MultiServerManager
from core.analytics_engine import AnalyticsEngine
from ai.predictive_analytics import PredictiveAnalytics
from ai.predictive_maintenance import PredictiveMaintenance
from core.realtime_monitor import RealtimeMonitor
from core.health_monitor import HealthMonitor
from core.webhook_manager import WebhookManager
from core.rbac import RBACManager
from core.alert_system import alert_system
from core.fleet_manager import fleet_manager
from security.auth import AuthManager, AuthenticationError, AuthorizationError
from core.enterprise import (
    custom_role_manager, server_permission_manager, get_ui_capabilities,
    parse_csv_import, maintenance_scheduler, rolling_update_orchestrator,
    ticketing_integration, server_lock_manager, task_manager,
)
from core.enterprise_extended import (
    shift_handoff_manager, knowledge_base_manager, investigation_share_manager,
    metric_history_store, custom_threshold_manager, incident_manager,
    sla_tracker, onboarding_manager, search_glossary, GLOSSARY,
    generate_investigation_html,
)
from core.enterprise_final import (
    custom_runbook_manager, investigation_feedback_manager,
    dashboard_layout_manager, bookmark_manager, executive_report_generator,
    comment_manager, saved_search_manager, get_vendor_support,
    compare_servers, export_for_bi,
)

# main.py (top imports)
from models.server_models import ActionLevel


# Configure structured JSON logging for production observability
import logging.handlers

_LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # "json" or "text"

if _LOG_FORMAT == "json":
    class _JsonFormatter(logging.Formatter):
        def format(self, record):
            log_obj = {
                "ts": self.formatTime(record, self.datefmt),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
                "module": record.module,
                "line": record.lineno,
            }
            if record.exc_info and record.exc_info[0]:
                log_obj["exception"] = self.formatException(record.exc_info)
            if hasattr(record, "correlation_id"):
                log_obj["correlation_id"] = record.correlation_id
            return json.dumps(log_obj, default=str)

    _handler = logging.StreamHandler()
    _handler.setFormatter(_JsonFormatter())
    logging.root.handlers = [_handler]
    logging.root.setLevel(logging.INFO)
else:
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
#  SECURITY INFRASTRUCTURE
# ═══════════════════════════════════════════════════════════════

# Auth manager (initialized on startup with config)
auth_manager: Optional[AuthManager] = None

# Rate limiter: per-IP request counts
_rate_limits: Dict[str, list] = defaultdict(list)

# Audit log — in-memory ring buffer + persistent append-only file for compliance
_audit_log: List[Dict[str, Any]] = []
_AUDIT_MAX = 10_000
_AUDIT_FILE = os.path.join(os.path.dirname(__file__) or '.', 'data', 'audit.jsonl')

def _ensure_audit_dir():
    os.makedirs(os.path.dirname(_AUDIT_FILE), exist_ok=True)

def _audit(event: str, *, ip: str = "?", user: str = "anonymous", detail: str = ""):
    """Append an event to the audit log (memory + persistent file)."""
    entry = {"ts": datetime.now().isoformat(), "event": event, "ip": ip, "user": user, "detail": detail}
    _audit_log.append(entry)
    if len(_audit_log) > _AUDIT_MAX:
        _audit_log.pop(0)
    # Append to immutable file (JSONL = one JSON object per line)
    try:
        _ensure_audit_dir()
        with open(_AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, default=str) + '\n')
    except Exception:
        pass  # file write is best-effort; in-memory log is authoritative
    logger.info(f"AUDIT [{event}] ip={ip} user={user} {detail}")

def _enforce_audit_retention():
    """Remove audit file entries older than retention period (#19)."""
    retention_days = int(os.getenv("LOG_RETENTION_DAYS", "30"))
    cutoff = datetime.now() - __import__('datetime').timedelta(days=retention_days)
    try:
        if not os.path.exists(_AUDIT_FILE):
            return
        kept = []
        with open(_AUDIT_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get('ts', '') >= cutoff.isoformat():
                        kept.append(line)
                except json.JSONDecodeError:
                    pass
        with open(_AUDIT_FILE, 'w', encoding='utf-8') as f:
            f.writelines(kept)
        logger.info(f"Audit retention enforced: kept {len(kept)} entries (cutoff {retention_days} days)")
    except Exception as e:
        logger.warning(f"Audit retention enforcement failed: {e}")

def _rate_check(ip: str, limit: int = 30, window: int = 60) -> bool:
    """Return True if request is within rate limit. Prunes old entries."""
    now = time.time()
    _rate_limits[ip] = [t for t in _rate_limits[ip] if now - t < window]
    if len(_rate_limits[ip]) >= limit:
        return False
    _rate_limits[ip].append(now)
    return True

def _sanitize_error(e: Exception) -> str:
    """Return a safe error message for the client. Log full detail server-side."""
    msg = str(e)
    # Strip file paths, stack traces, internal IPs, and technical details
    lower = msg.lower()
    if any(tok in lower for tok in ['traceback', 'file "/', 'file "c:', 'file "\\\\',
                                     'modulenotfound', 'errno', 'econnrefused', 'econnreset']):
        return "An internal error occurred. Please try again."
    # Strip internal IPs from messages
    msg = re.sub(r'\b(?:10|172\.(?:1[6-9]|2\d|3[01])|192\.168)\.\d{1,3}\.\d{1,3}\b', '[server]', msg)
    # Keep short operational messages that are useful to the technician
    if len(msg) > 300:
        return msg[:297] + "..."
    return msg

# Hostnames: allow IPs (v4/v6), FQDNs. Block obvious path-traversal.
_HOST_RE = re.compile(r'^[a-zA-Z0-9._:\-\[\]]+$')

def _validate_host(host: str) -> str:
    """Validate and sanitize a hostname/IP. Raises HTTPException on bad input."""
    host = host.strip()
    if not host or len(host) > 253:
        raise HTTPException(status_code=400, detail="Invalid host")
    if not _HOST_RE.match(host):
        raise HTTPException(status_code=400, detail="Invalid host format")
    return host

# OS command whitelist — only these actions are allowed via /api/os/execute
_OS_COMMAND_WHITELIST = {
    # Match the actual action names used by the /api/os/execute handler
    'os_info', 'system_resources', 'running_processes', 'services',
    'network_info', 'os_logs', 'storage_info', 'installed_packages',
    'hardware_info', 'service_status', 'restart_service',
    'custom_command',  # custom_command only for admin role
}

# ─── Correlation ID Middleware ────────────────────────────────
import uuid as _uuid

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique correlation ID to every request for distributed tracing."""
    async def dispatch(self, request: Request, call_next):
        cid = request.headers.get("X-Correlation-ID") or str(_uuid.uuid4())
        request.state.correlation_id = cid
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = cid
        return response

# ─── Security Headers Middleware ─────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to every response."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        # CSP: allow self + inline styles (needed by dashboard) + CDN fonts
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net; "
            "font-src 'self' https://fonts.gstatic.com https://cdn.jsdelivr.net; "
            "img-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
        )
        return response

# ─── Rate-Limit Middleware ───────────────────────────────────
class RateLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests that exceed per-IP rate limits."""
    # Tighter limits for sensitive paths
    SENSITIVE = {'/api/connect': 120, '/api/os/connect': 120, '/api/os/execute': 300,
                 '/api/auth/login': 120, '/api/execute': 600, '/api/chat': 300,
                 '/api/chat/stream': 300}
    
    async def dispatch(self, request: Request, call_next):
        ip = request.client.host if request.client else "unknown"
        path = request.url.path
        limit = self.SENSITIVE.get(path, 1000)  # 1000 req/min default
        if not _rate_check(ip, limit=limit, window=60):
            _audit("RATE_LIMIT", ip=ip, detail=path)
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Please slow down."})
        return await call_next(request)

# ─── Auth dependency (FastAPI Depends) ───────────────────────
async def _get_current_user(request: Request) -> Dict[str, Any]:
    """Extract and validate the JWT token from Authorization header or cookie.
    Returns user info dict or raises 401.
    """
    token = None
    # 1. Authorization: Bearer <token>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    # 2. Cookie fallback (for browser pages)
    if not token:
        token = request.cookies.get("auth_token")
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        user_info = await auth_manager.validate_token(token)
        return user_info
    except AuthenticationError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def _require_role(request: Request, role: str) -> Dict[str, Any]:
    """Ensure the current user has a specific role."""
    user = await _get_current_user(request)
    if user.get("role") != role and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user

async def _require_permission(request: Request, perm: str) -> Dict[str, Any]:
    """Ensure the current user has a specific permission."""
    user = await _get_current_user(request)
    if perm not in user.get("permissions", []):
        raise HTTPException(status_code=403, detail="Insufficient permissions")
    return user

# Initialize FastAPI app
app = FastAPI(
    title="Medi-AI-tor",
    description="AI-powered Dell server diagnostics and management",
    version="1.0.0"
)

# CORS middleware — restrict origins; defaults to localhost in dev (#60)
_cors_origins = os.getenv("CORS_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else []
if not _allowed_origins:
    _allowed_origins = ["http://localhost:8000", "http://localhost:3000", "http://127.0.0.1:8000"]
    logger.info("CORS_ORIGINS not set — defaulting to localhost only (set CORS_ORIGINS for production)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
)

# Security headers, rate limiting, correlation IDs
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(CorrelationIdMiddleware)

# Initialize global components
# Per-session connection manager replaces the old global agent singleton.
# Each authenticated user gets their own DellAIAgent + AgentBrain so that
# connecting to Server-A on one session does NOT affect another session.
session_mgr: Optional[SessionConnectionManager] = None
app_config = None  # AgentConfig — shared read-only config
automation_engine = None
multi_server_manager = None
analytics_engine = None
predictive_analytics = None
predictive_maintenance = None
voice_assistant = None
ssh_client = None  # OS-level SSH connection
third_party_api = None
realtime_monitor = None
health_monitor = None
webhook_manager = None
rbac_manager = None

# ─── Per-Session Connection Helpers ──────────────────────────────
async def _get_session_conn(request: Request):
    """Resolve the current user's per-session agent + brain.
    
    For authenticated endpoints: extracts session_id from JWT → 
    returns (or creates) a dedicated DellAIAgent + AgentBrain.
    """
    user = await _get_current_user(request)
    sid = user.get("session_id", user.get("username", "anonymous"))
    conn = await session_mgr.get_or_create(sid, user.get("username", "anonymous"))
    return conn, user

async def _get_default_conn():
    """Get the shared default connection (for unauthenticated customer endpoints)."""
    return await session_mgr.get_default()

# Pydantic models for API
class ServerConnection(BaseModel):
    host: str = ""
    username: str = ""
    password: str = ""
    port: Optional[Union[str, int]] = 443
    serverHost: Optional[str] = None  # UI field name
    
    def get_port(self) -> int:
        """Get port as integer"""
        if isinstance(self.port, str):
            try:
                return int(self.port)
            except ValueError:
                return 443
        return self.port or 443
    
    def get_host(self) -> str:
        """Get host from either field"""
        return self.serverHost or self.host
    
    def get_username(self) -> str:
        """Get username"""
        return self.username
    
    def get_password(self) -> str:
        """Get password"""
        return self.password

class AgentActionRequest(BaseModel):
    action: str
    action_level: ActionLevel
    command: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = {}

class TroubleshootingTask(BaseModel):
    server_info: ServerConnection
    issue_description: str
    action_level: ActionLevel = ActionLevel.READ_ONLY

class ChatMessage(BaseModel):
    message: str
    action_level: ActionLevel = ActionLevel.READ_ONLY

class OSConnection(BaseModel):
    host: str
    username: str
    password: Optional[str] = None
    port: int = 22
    key_file: Optional[str] = None

@app.on_event("startup")
async def startup_event():
    """Initialize the AI agent and all components on startup"""
    global session_mgr, app_config, automation_engine, multi_server_manager, analytics_engine
    global predictive_analytics, predictive_maintenance, voice_assistant, third_party_api
    global realtime_monitor, health_monitor, webhook_manager, rbac_manager
    global auth_manager
    
    config = AgentConfig.from_env()
    app_config = config
    
    if config.demo_mode:
        logger.info("*** DEMO MODE ENABLED — using simulated server data ***")
    
    if not config.verify_ssl:
        logger.warning("SSL certificate verification is DISABLED (VERIFY_SSL=false). "
                       "This is acceptable for iDRAC with self-signed certs but should be "
                       "enabled in production with proper CA bundles.")
    
    if not config.require_https:
        logger.warning("HTTPS is NOT required (REQUIRE_HTTPS=false). "
                       "Enable in production to protect credentials in transit.")
    
    # Initialize per-session connection manager (replaces old global agent singleton)
    session_mgr = SessionConnectionManager(config, max_sessions=100, idle_timeout_min=60)
    logger.info("Per-session connection manager initialized (max 100 sessions, 60 min idle timeout)")
    
    # Initialize shared services
    realtime_monitor = RealtimeMonitor()
    health_monitor = HealthMonitor()
    webhook_manager = WebhookManager()
    rbac_manager = RBACManager()
    predictive_analytics = PredictiveAnalytics(config)
    predictive_maintenance = PredictiveMaintenance(predictive_analytics)
    analytics_engine = AnalyticsEngine()
    
    # Create a default agent for automation engine (uses default session)
    default_conn = await session_mgr.get_default()
    automation_engine = AutomationEngine(default_conn.agent)
    multi_server_manager = MultiServerManager(config)
    
    # Initialize authentication (passwords loaded from env by AuthManager)
    auth_manager = AuthManager(config)
    logger.info("Authentication system initialized (3 default roles: admin, operator, viewer)")
    
    # Optional components (may not exist)
    try:
        from integrations.voice_assistant import VoiceAssistant
        voice_assistant = VoiceAssistant(default_conn.agent)
    except ImportError:
        voice_assistant = None
    
    try:
        from api.third_party_api import ThirdPartyAPI
        third_party_api = ThirdPartyAPI(default_conn.agent)
    except ImportError:
        third_party_api = None
    
    logger.info("Medi-AI-tor and all components initialized successfully")
    
    # Load persisted fleet state from previous session
    try:
        fleet_path = os.path.join(os.path.dirname(__file__) or '.', 'data', 'fleet_state.json')
        if os.path.exists(fleet_path):
            with open(fleet_path, 'r') as f:
                fleet_data = json.load(f)
            loaded = 0
            for sid, sdata in fleet_data.items():
                if sid not in fleet_manager.servers:
                    try:
                        fleet_manager.add_server(
                            name=sdata.get('name', 'Unknown'),
                            host=sdata.get('host', ''),
                            username=sdata.get('username', ''),
                            password=sdata.get('password', ''),
                            port=sdata.get('port', 443),
                            model=sdata.get('model'),
                            service_tag=sdata.get('service_tag'),
                            environment=sdata.get('environment', 'production'),
                            _already_encrypted=True,
                        )
                        loaded += 1
                    except Exception as e:
                        logger.warning(f"Could not restore fleet server {sdata.get('name')}: {e}")
            if loaded:
                logger.info(f"Restored {loaded} server(s) from fleet state")
    except Exception as e:
        logger.warning(f"Fleet state load: {e}")

    # Enforce data retention policy on startup (#19)
    _enforce_audit_retention()

@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown — drain connections, stop monitoring, persist state."""
    logger.info("Shutting down Medi-AI-tor...")
    
    # Stop health monitoring
    try:
        if health_monitor:
            health_monitor.stop_all()
            logger.info("Health monitors stopped")
    except Exception as e:
        logger.warning(f"Health monitor shutdown: {e}")
    
    # Stop realtime monitoring
    try:
        if realtime_monitor and realtime_monitor.monitoring_active:
            await realtime_monitor.stop_monitoring()
            logger.info("Realtime monitor stopped")
    except Exception as e:
        logger.warning(f"Realtime monitor shutdown: {e}")
    
    # Disconnect from iDRAC
    try:
        if session_mgr:
            await session_mgr.shutdown()
            logger.info("All session connections closed")
    except Exception as e:
        logger.warning(f"Session manager shutdown: {e}")
    
    # Persist fleet data to disk (including encrypted passwords for reconnection)
    try:
        if fleet_manager and fleet_manager.servers:
            import json, os
            data_dir = os.path.join(os.path.dirname(__file__), 'data')
            os.makedirs(data_dir, exist_ok=True)
            fleet_path = os.path.join(data_dir, 'fleet_state.json')
            fleet_data = {}
            for sid, s in fleet_manager.servers.items():
                d = s.to_dict()
                d['password'] = s.password  # Include encrypted password for persistence
                fleet_data[sid] = d
            with open(fleet_path, 'w') as f:
                json.dump(fleet_data, f, indent=2, default=str)
            logger.info(f"Fleet state persisted to {fleet_path} ({len(fleet_data)} servers)")
    except Exception as e:
        logger.warning(f"Fleet persistence during shutdown: {e}")
    
    # Clean up auth sessions
    try:
        if auth_manager:
            auth_manager.cleanup_expired_sessions()
            logger.info(f"Auth sessions cleaned up ({len(auth_manager.sessions)} active)")
    except Exception as e:
        logger.warning(f"Auth cleanup during shutdown: {e}")
    
    logger.info("Medi-AI-tor shutdown complete")

# ═══════════════════════════════════════════════════════════════
#  ENTERPRISE FEATURES API — Gaps #21-#30
# ═══════════════════════════════════════════════════════════════

# #23: UI Capabilities (role-based feature gating)
@app.get("/api/auth/capabilities")
async def auth_capabilities(request: Request):
    """Return UI feature flags based on user's role and permissions."""
    user = await _get_current_user(request)
    caps = get_ui_capabilities(user["role"], user["permissions"])
    return {"status": "success", "capabilities": caps, "role": user["role"]}

# #22: Custom Roles CRUD
@app.get("/api/roles")
async def list_roles(request: Request):
    user = await _get_current_user(request)
    return {"status": "success", "roles": custom_role_manager.list_roles()}

@app.post("/api/roles")
async def create_role(request: Request):
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    try:
        role = custom_role_manager.create_role(body["name"], body["permissions"], body.get("description", ""))
        _audit("ROLE_CREATED", user=user["username"], detail=body["name"])
        return {"status": "success", "role": role}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# #21: Per-server permissions
@app.post("/api/permissions/scope")
async def set_user_scope(request: Request):
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    body = await request.json()
    server_permission_manager.set_user_scope(
        body["username"], body.get("server_ids"), body.get("group_names"))
    _audit("SCOPE_SET", user=user["username"], detail=f"scope for {body['username']}")
    return {"status": "success"}

@app.get("/api/permissions/scope/{username}")
async def get_user_scope(username: str, request: Request):
    user = await _get_current_user(request)
    return {"status": "success", "scope": server_permission_manager.get_user_scope(username)}

# #24: Bulk CSV import
@app.post("/api/fleet/import/csv")
async def bulk_import_csv(request: Request):
    user = await _get_current_user(request)
    if "fleet_manage" not in user.get("permissions", []) and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Fleet management permission required")
    body = await request.json()
    csv_content = body.get("csv", "")
    if not csv_content:
        raise HTTPException(status_code=400, detail="csv field required")
    try:
        servers = parse_csv_import(csv_content)
        added = []
        for s in servers:
            sid = fleet_manager.add_server(
                name=s["name"], host=s["host"], username=s["username"], password=s["password"],
                port=s["port"], environment=s.get("environment"), location=s.get("location"),
                tags=s.get("tags"), notes=s.get("notes"))
            added.append(sid)
        _audit("BULK_IMPORT", user=user["username"], detail=f"{len(added)} servers imported")
        return {"status": "success", "imported": len(added), "server_ids": added}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# #25: Maintenance Windows
@app.post("/api/maintenance")
async def schedule_maintenance(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    try:
        mw = maintenance_scheduler.schedule(
            server_ids=body["server_ids"],
            start=datetime.fromisoformat(body["start_time"]),
            end=datetime.fromisoformat(body["end_time"]),
            description=body.get("description", ""),
            created_by=user["username"],
            group_name=body.get("group_name"),
            suppress_alerts=body.get("suppress_alerts", True),
        )
        _audit("MAINTENANCE_SCHEDULED", user=user["username"], detail=mw.id)
        return {"status": "success", "window": {"id": mw.id, "status": mw.status}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/maintenance")
async def list_maintenance(request: Request):
    await _get_current_user(request)
    return {"status": "success", "windows": maintenance_scheduler.list_windows()}

@app.delete("/api/maintenance/{window_id}")
async def cancel_maintenance(window_id: str, request: Request):
    user = await _get_current_user(request)
    try:
        maintenance_scheduler.cancel(window_id)
        _audit("MAINTENANCE_CANCELLED", user=user["username"], detail=window_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# #26: Rolling Firmware Updates
@app.post("/api/fleet/rolling-update")
async def create_rolling_update(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    plan = rolling_update_orchestrator.create_plan(
        server_ids=body["server_ids"], component=body["component"],
        version=body["version"], batch_size=body.get("batch_size", 5),
        created_by=user["username"], health_gate=body.get("health_gate", True))
    _audit("ROLLING_UPDATE_CREATED", user=user["username"], detail=plan.id)
    return {"status": "success", "plan": rolling_update_orchestrator.get_plan_status(plan.id)}

@app.get("/api/fleet/rolling-update")
async def list_rolling_updates(request: Request):
    await _get_current_user(request)
    return {"status": "success", "plans": rolling_update_orchestrator.list_plans()}

@app.get("/api/fleet/rolling-update/{plan_id}")
async def get_rolling_update(plan_id: str, request: Request):
    await _get_current_user(request)
    status = rolling_update_orchestrator.get_plan_status(plan_id)
    if not status:
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"status": "success", "plan": status}

# #28: Ticketing Integration
@app.post("/api/tickets")
async def link_ticket(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    ticket = ticketing_integration.link_ticket(
        sr_number=body["sr_number"], server_id=body.get("server_id", ""),
        investigation_id=body.get("investigation_id"),
        summary=body.get("summary", ""), priority=body.get("priority", "medium"))
    _audit("TICKET_LINKED", user=user["username"], detail=body["sr_number"])
    return {"status": "success", "ticket": ticket}

@app.get("/api/tickets")
async def list_tickets(request: Request):
    await _get_current_user(request)
    return {"status": "success", "tickets": ticketing_integration.list_open_tickets()}

@app.get("/api/tickets/server/{server_id}")
async def get_server_tickets(server_id: str, request: Request):
    await _get_current_user(request)
    return {"status": "success", "tickets": ticketing_integration.get_tickets_for_server(server_id)}

# #29: Server Locking
@app.post("/api/servers/{server_id}/lock")
async def lock_server(server_id: str, request: Request):
    user = await _get_current_user(request)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    try:
        lock = server_lock_manager.acquire(server_id, user["username"], body.get("reason", ""))
        return {"status": "success", "lock": {"server_id": server_id, "locked_by": user["username"],
                "expires_at": lock.expires_at.isoformat() if lock.expires_at else None}}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@app.delete("/api/servers/{server_id}/lock")
async def unlock_server(server_id: str, request: Request):
    user = await _get_current_user(request)
    try:
        server_lock_manager.release(server_id, user["username"])
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=403, detail=str(e))

@app.get("/api/servers/{server_id}/lock")
async def check_server_lock(server_id: str, request: Request):
    await _get_current_user(request)
    lock = server_lock_manager.is_locked(server_id)
    return {"status": "success", "locked": lock is not None, "lock": lock}

# #30: Task Assignment / Work Queue
@app.post("/api/tasks")
async def create_task(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    task = task_manager.create_task(
        title=body["title"], description=body.get("description", ""),
        created_by=user["username"], server_id=body.get("server_id"),
        assigned_to=body.get("assigned_to"), priority=body.get("priority", "medium"),
        sr_number=body.get("sr_number"))
    _audit("TASK_CREATED", user=user["username"], detail=task.id)
    return {"status": "success", "task": task_manager.get_queue(status=None)[0] if task_manager.tasks else {}}

@app.get("/api/tasks")
async def list_tasks(request: Request, assigned_to: str = None, status: str = None):
    await _get_current_user(request)
    return {"status": "success", "tasks": task_manager.get_queue(assigned_to, status),
            "stats": task_manager.get_stats()}

@app.put("/api/tasks/{task_id}/assign")
async def assign_task(task_id: str, request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    try:
        task_manager.assign(task_id, body["username"])
        _audit("TASK_ASSIGNED", user=user["username"], detail=f"{task_id} -> {body['username']}")
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/tasks/{task_id}/complete")
async def complete_task(task_id: str, request: Request):
    user = await _get_current_user(request)
    try:
        task_manager.complete(task_id)
        _audit("TASK_COMPLETED", user=user["username"], detail=task_id)
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ═══════════════════════════════════════════════════════════════
#  ENTERPRISE EXTENDED API — Gaps #31-#40
# ═══════════════════════════════════════════════════════════════

# #31: Shift Handoff
@app.post("/api/handoff")
async def create_handoff(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    h = shift_handoff_manager.create(
        from_user=user["username"], shift=body.get("shift", ""),
        summary=body.get("summary", ""), open_issues=body.get("open_issues"),
        server_notes=body.get("server_notes"), priority_items=body.get("priority_items"),
        to_user=body.get("to_user"))
    _audit("HANDOFF_CREATED", user=user["username"], detail=h.id)
    return {"status": "success", "handoff_id": h.id}

@app.get("/api/handoff")
async def list_handoffs(request: Request, shift: str = None):
    await _get_current_user(request)
    return {"status": "success", "handoffs": shift_handoff_manager.get_latest(shift)}

@app.post("/api/handoff/{handoff_id}/acknowledge")
async def acknowledge_handoff(handoff_id: str, request: Request):
    user = await _get_current_user(request)
    try:
        shift_handoff_manager.acknowledge(handoff_id, user["username"])
        return {"status": "success"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# #32: Knowledge Base
@app.get("/api/kb")
async def search_kb(request: Request, q: str = "", category: str = None):
    await _get_current_user(request)
    if q:
        return {"status": "success", "results": knowledge_base_manager.search(q, category)}
    return {"status": "success", "stats": knowledge_base_manager.get_stats()}

@app.get("/api/kb/{article_id}")
async def get_kb_article(article_id: str, request: Request):
    await _get_current_user(request)
    article = knowledge_base_manager.get_article(article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    return {"status": "success", "article": article}

@app.post("/api/kb")
async def create_kb_article(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    if "diagnosis" in body:
        article = knowledge_base_manager.add_from_investigation(body["diagnosis"], user["username"], body.get("sr_number"))
    else:
        article = knowledge_base_manager.add_manual(
            title=body["title"], root_cause=body.get("root_cause",""),
            symptoms=body.get("symptoms",[]), resolution=body.get("resolution",""),
            category=body.get("category","general"), created_by=user["username"],
            tags=body.get("tags"), server_model=body.get("server_model"))
    _audit("KB_ARTICLE_CREATED", user=user["username"], detail=article.id)
    return {"status": "success", "article_id": article.id}

# #33: Investigation Sharing
@app.post("/api/investigations/share")
async def share_investigation(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    s = investigation_share_manager.share(
        investigation_data=body.get("investigation", {}), shared_by=user["username"],
        shared_with=body.get("shared_with"), notes=body.get("notes",""),
        server_id=body.get("server_id"), sr_number=body.get("sr_number"))
    _audit("INVESTIGATION_SHARED", user=user["username"], detail=s.id)
    return {"status": "success", "share_id": s.id}

@app.get("/api/investigations/shared")
async def get_shared_investigations(request: Request):
    user = await _get_current_user(request)
    return {"status": "success", "investigations": investigation_share_manager.get_shared_with_user(user["username"])}

@app.get("/api/investigations/shared/{share_id}")
async def get_shared_investigation(share_id: str, request: Request):
    await _get_current_user(request)
    result = investigation_share_manager.get_full(share_id)
    if not result:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "success", "investigation": result}

# #34: Extended Metric History
@app.get("/api/metrics/history")
async def get_metric_history_extended(request: Request, server_id: str = None,
                                       hours: int = Query(default=24, ge=1, le=720),
                                       metric: str = None):
    await _get_current_user(request)
    data = metric_history_store.query(server_id, hours, metric)
    return {"status": "success", "points": len(data), "data": data[:2000],
            "stats": metric_history_store.get_stats()}

# #35: Custom Thresholds
@app.post("/api/thresholds")
async def set_custom_threshold(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    custom_threshold_manager.set_threshold(
        scope=body["scope"], metric=body["metric"],
        warning=body.get("warning"), critical=body.get("critical"))
    _audit("THRESHOLD_SET", user=user["username"], detail=f"{body['scope']}/{body['metric']}")
    return {"status": "success"}

@app.get("/api/thresholds")
async def list_thresholds(request: Request, scope: str = None):
    await _get_current_user(request)
    return {"status": "success", "thresholds": custom_threshold_manager.list_overrides(scope)}

# #36: Incident Management
@app.post("/api/incidents")
async def create_incident(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    inc = incident_manager.create_incident(
        title=body["title"], description=body.get("description",""),
        severity=body.get("severity","medium"), server_id=body.get("server_id"),
        created_by=user["username"])
    _audit("INCIDENT_CREATED", user=user["username"], detail=inc["id"])
    return {"status": "success", "incident": inc}

@app.get("/api/incidents")
async def list_incidents(request: Request, status: str = None):
    await _get_current_user(request)
    return {"status": "success", "incidents": incident_manager.list_incidents(status)}

@app.post("/api/incidents/{incident_id}/resolve")
async def resolve_incident_api(incident_id: str, request: Request):
    user = await _get_current_user(request)
    try:
        inc = incident_manager.resolve_incident(incident_id, user["username"])
        _audit("INCIDENT_RESOLVED", user=user["username"], detail=incident_id)
        return {"status": "success", "incident": inc}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# #37: SLA Tracking
@app.get("/api/sla/{server_id}")
async def get_server_sla(server_id: str, request: Request, days: int = Query(default=30, ge=1, le=365)):
    await _get_current_user(request)
    return {"status": "success", "sla": sla_tracker.get_sla_report(server_id, days)}

@app.get("/api/sla")
async def get_fleet_sla(request: Request, days: int = Query(default=30, ge=1, le=365)):
    await _get_current_user(request)
    server_ids = list(fleet_manager.servers.keys()) if fleet_manager else []
    return {"status": "success", "sla": sla_tracker.get_fleet_sla(server_ids, days)}

# #38: Onboarding
@app.get("/api/onboarding")
async def get_onboarding(request: Request):
    user = await _get_current_user(request)
    return {"status": "success", "onboarding": onboarding_manager.get_progress(user["username"])}

@app.post("/api/onboarding/{step_id}")
async def complete_onboarding_step(step_id: str, request: Request):
    user = await _get_current_user(request)
    progress = onboarding_manager.complete_step(user["username"], step_id)
    return {"status": "success", "onboarding": progress}

# #39: Glossary
@app.get("/api/glossary")
async def get_glossary(request: Request, q: str = None):
    # Public — no auth required for glossary
    if q:
        return {"status": "success", "results": search_glossary(q)}
    return {"status": "success", "glossary": list(GLOSSARY.values()), "total": len(GLOSSARY)}

# #40: Investigation Report Export (HTML)
@app.post("/api/investigations/export/html")
async def export_investigation_html(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    investigation = body.get("investigation", {})
    server_info = body.get("server_info")
    html = generate_investigation_html(investigation, server_info)
    _audit("REPORT_EXPORTED", user=user["username"], detail="html")
    return HTMLResponse(content=html, headers={
        "Content-Disposition": f'attachment; filename="investigation-report-{datetime.now().strftime("%Y%m%d-%H%M%S")}.html"'
    })

# ═══════════════════════════════════════════════════════════════
#  ENTERPRISE FINAL API — Gaps #41-#67
# ═══════════════════════════════════════════════════════════════

# #41: Custom Runbooks
@app.post("/api/runbooks")
async def add_runbook(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    rb = custom_runbook_manager.add_runbook(
        title=body["title"], symptoms=body.get("symptoms",[]),
        steps=body.get("steps",[]), category=body.get("category","general"),
        created_by=user["username"], priority=body.get("priority",5))
    _audit("RUNBOOK_CREATED", user=user["username"], detail=rb["id"])
    return {"status":"success","runbook":rb}

@app.get("/api/runbooks")
async def list_runbooks(request: Request):
    await _get_current_user(request)
    return {"status":"success","data":custom_runbook_manager.list_all()}

@app.get("/api/runbooks/match")
async def match_runbooks(request: Request, issue: str = ""):
    await _get_current_user(request)
    return {"status":"success","matches":custom_runbook_manager.match_runbooks(issue)}

# #42: Investigation Feedback
@app.post("/api/feedback")
async def submit_feedback(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    fb = investigation_feedback_manager.submit(
        investigation_id=body.get("investigation_id",""),
        was_correct=body.get("was_correct",True),
        actual_cause=body.get("actual_cause",""),
        notes=body.get("notes",""), submitted_by=user["username"])
    _audit("FEEDBACK_SUBMITTED", user=user["username"], detail=fb["id"])
    return {"status":"success","feedback":fb}

@app.get("/api/feedback/stats")
async def get_feedback_stats(request: Request):
    await _get_current_user(request)
    return {"status":"success","stats":investigation_feedback_manager.get_accuracy_stats(),
            "recent":investigation_feedback_manager.list_feedback(20)}

# #43: Multi-vendor support info
@app.get("/api/vendors")
async def get_vendors(request: Request):
    return {"status":"success","vendors":get_vendor_support()}

# #44: Dashboard Layout
@app.post("/api/dashboard/layout")
async def save_dashboard_layout(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    layout = dashboard_layout_manager.save_layout(user["username"], body)
    return {"status":"success","layout":layout}

@app.get("/api/dashboard/layout")
async def get_dashboard_layout(request: Request):
    user = await _get_current_user(request)
    layout = dashboard_layout_manager.get_layout(user["username"])
    return {"status":"success","layout":layout}

# #46: Bookmarks
@app.post("/api/bookmarks/{server_id}")
async def add_bookmark(server_id: str, request: Request):
    user = await _get_current_user(request)
    bookmark_manager.add(user["username"], server_id)
    return {"status":"success"}

@app.delete("/api/bookmarks/{server_id}")
async def remove_bookmark(server_id: str, request: Request):
    user = await _get_current_user(request)
    bookmark_manager.remove(user["username"], server_id)
    return {"status":"success"}

@app.get("/api/bookmarks")
async def get_bookmarks(request: Request):
    user = await _get_current_user(request)
    return {"status":"success","bookmarks":bookmark_manager.get(user["username"])}

# #50: Executive Reports
@app.get("/api/reports/executive")
async def get_executive_report(request: Request):
    user = await _get_current_user(request)
    fleet_overview = fleet_manager.get_fleet_overview() if fleet_manager else {}
    sla_data = sla_tracker.get_fleet_sla(list(fleet_manager.servers.keys())) if fleet_manager else {}
    report = executive_report_generator.generate_executive_summary(
        fleet_overview, sla_data, len(incident_manager.incidents), len(knowledge_base_manager.articles))
    return {"status":"success","report":report}

@app.get("/api/reports/technician-metrics")
async def get_technician_metrics(request: Request, username: str = None, days: int = Query(default=30,ge=1,le=365)):
    await _get_current_user(request)
    return {"status":"success","metrics":executive_report_generator.get_technician_metrics(username,days)}

# #51: BI Export
@app.get("/api/export/bi")
async def export_bi_data(request: Request, dataset: str = "fleet", format: str = "csv"):
    user = await _get_current_user(request)
    if dataset == "fleet":
        data = [s.to_dict() for s in fleet_manager.servers.values()] if fleet_manager else []
    elif dataset == "incidents":
        data = incident_manager.list_incidents()
    elif dataset == "sla":
        data = [sla_tracker.get_sla_report(sid) for sid in (fleet_manager.servers.keys() if fleet_manager else [])]
    else:
        raise HTTPException(status_code=400, detail=f"Unknown dataset: {dataset}. Use: fleet, incidents, sla")
    content = export_for_bi(data, format)
    media = "text/csv" if format == "csv" else "application/json"
    from starlette.responses import PlainTextResponse
    return PlainTextResponse(content, media_type=media, headers={
        "Content-Disposition": f'attachment; filename="{dataset}-{datetime.now().strftime("%Y%m%d")}.{format}"'})

# #64: Comments / @Mentions
@app.post("/api/servers/{server_id}/comments")
async def add_comment(server_id: str, request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    comment = comment_manager.add_comment(server_id, body.get("text",""), user["username"])
    return {"status":"success","comment":comment}

@app.get("/api/servers/{server_id}/comments")
async def get_comments(server_id: str, request: Request):
    await _get_current_user(request)
    return {"status":"success","comments":comment_manager.get_comments(server_id)}

@app.get("/api/mentions")
async def get_mentions(request: Request):
    user = await _get_current_user(request)
    return {"status":"success","mentions":comment_manager.get_mentions(user["username"])}

# #65: Server Comparison
@app.post("/api/fleet/compare")
async def compare_fleet_servers(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    ids = body.get("server_ids",[])
    servers = [fleet_manager.servers[sid].to_dict() for sid in ids if sid in fleet_manager.servers]
    return {"status":"success","comparison":compare_servers(servers)}

# #66: Saved Searches
@app.post("/api/searches")
async def save_search(request: Request):
    user = await _get_current_user(request)
    body = await request.json()
    s = saved_search_manager.save(user["username"], body.get("name",""), body.get("filters",{}))
    return {"status":"success","search":s}

@app.get("/api/searches")
async def list_searches(request: Request):
    user = await _get_current_user(request)
    return {"status":"success","searches":saved_search_manager.get(user["username"])}

@app.delete("/api/searches/{search_id}")
async def delete_search(search_id: str, request: Request):
    user = await _get_current_user(request)
    saved_search_manager.delete(user["username"], search_id)
    return {"status":"success"}

# #52: Paginated fleet endpoint
@app.get("/api/v1/fleet/servers")
async def list_fleet_servers_paginated(request: Request,
        page: int = Query(default=1, ge=1), per_page: int = Query(default=50, ge=1, le=200),
        environment: str = None, status: str = None, datacenter: str = None):
    """Paginated, filterable server list (#52, #58 API versioning)."""
    user = await _get_current_user(request)
    all_servers = list(fleet_manager.servers.values()) if fleet_manager else []
    # Filter
    if environment:
        all_servers = [s for s in all_servers if s.environment == environment]
    if status:
        all_servers = [s for s in all_servers if (s.status.value if hasattr(s.status,'value') else s.status) == status]
    if datacenter:
        all_servers = [s for s in all_servers if getattr(s,'datacenter','') == datacenter]
    total = len(all_servers)
    start = (page - 1) * per_page
    page_servers = all_servers[start:start + per_page]
    return {"status":"success","data":[s.to_dict() for s in page_servers],
            "pagination":{"page":page,"per_page":per_page,"total":total,
                          "pages":(total + per_page - 1) // per_page if per_page else 1}}

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# ═══════════════════════════════════════════════════════════════
#  AUTHENTICATION ENDPOINTS
# ═══════════════════════════════════════════════════════════════

class LoginRequest(BaseModel):
    username: str
    password: str

@app.get("/login", response_class=HTMLResponse)
async def get_login_page():
    """Serve the login page — inlined to bypass service worker cache."""
    import pathlib
    html = (pathlib.Path(__file__).parent / 'templates' / 'login.html').read_text(encoding='utf-8')
    return HTMLResponse(content=html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Clear-Site-Data": '"cache", "storage"',
    })

@app.post("/api/auth/login")
async def auth_login(creds: LoginRequest, request: Request):
    """Authenticate user and return JWT token"""
    ip = request.client.host if request.client else "unknown"
    try:
        result = await auth_manager.authenticate(creds.username, creds.password)
        _audit("LOGIN_SUCCESS", ip=ip, user=creds.username)
        response = JSONResponse(content={"status": "success", **result})
        # Set HTTP-only cookie for browser-based access
        response.set_cookie(
            key="auth_token",
            value=result["token"],
            httponly=True,
            samesite="strict",
            max_age=86400,  # 24 hours
            secure=os.getenv("REQUIRE_HTTPS", "false").lower() == "true",
        )
        return response
    except AuthenticationError as e:
        _audit("LOGIN_FAILED", ip=ip, user=creds.username, detail=str(e))
        raise HTTPException(status_code=401, detail="Invalid username or password")

@app.post("/api/auth/logout")
async def auth_logout(request: Request):
    """Logout and invalidate session"""
    try:
        user = await _get_current_user(request)
        await auth_manager.logout(user.get("session_id", ""))
        _audit("LOGOUT", user=user.get("username", "?"))
        response = JSONResponse(content={"status": "success"})
        response.delete_cookie("auth_token")
        return response
    except Exception:
        response = JSONResponse(content={"status": "success"})
        response.delete_cookie("auth_token")
        return response

@app.get("/api/auth/me")
async def auth_me(request: Request):
    """Get current user info (validates token)"""
    user = await _get_current_user(request)
    return {"status": "success", "user": user}

@app.post("/api/auth/refresh")
async def auth_refresh(request: Request):
    """Refresh an expired access token using a valid refresh token."""
    body = await request.json()
    refresh_token = body.get("refresh_token", "")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="refresh_token is required")
    try:
        result = await auth_manager.refresh_access_token(refresh_token)
        response = JSONResponse(content={"status": "success", **result})
        response.set_cookie(
            key="auth_token", value=result["token"],
            httponly=True, samesite="strict",
            max_age=result["expires_in"],
            secure=os.getenv("REQUIRE_HTTPS", "false").lower() == "true",
        )
        return response
    except AuthenticationError as e:
        raise HTTPException(status_code=401, detail=str(e))

@app.post("/api/auth/change-password")
async def auth_change_password(request: Request, body: dict):
    """Change current user's password"""
    user = await _get_current_user(request)
    try:
        await auth_manager.change_password(
            user["username"], body.get("old_password", ""), body.get("new_password", "")
        )
        _audit("PASSWORD_CHANGE", user=user["username"])
        return {"status": "success", "message": "Password changed"}
    except AuthenticationError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/auth/sessions")
async def auth_sessions(request: Request):
    """List active sessions (admin only)"""
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"status": "success", "sessions": auth_manager.get_active_sessions()}

@app.get("/api/audit-log")
async def get_audit_log(request: Request, limit: int = Query(default=100, le=1000)):
    """Get recent audit log entries (admin only)"""
    user = await _get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return {"status": "success", "entries": _audit_log[-limit:]}

# ═══════════════════════════════════════════════════════════════
#  PAGE ROUTES
# ═══════════════════════════════════════════════════════════════

@app.get("/reset", response_class=HTMLResponse)
async def reset_browser_cache():
    """Nuclear cache reset — clears service workers, caches, storage, then redirects to login."""
    return HTMLResponse(content="""<!DOCTYPE html>
<html><head><title>Clearing cache...</title></head>
<body style="background:#0f172a;color:#f1f5f9;font-family:sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0">
<div style="text-align:center">
<h2>Clearing browser cache...</h2>
<p id="status">Removing stale data...</p>
<script>
(async function(){
    const s = document.getElementById('status');
    try {
        // 1. Unregister ALL service workers
        if ('serviceWorker' in navigator) {
            const regs = await navigator.serviceWorker.getRegistrations();
            for (const r of regs) { await r.unregister(); }
            s.textContent = 'Service workers removed (' + regs.length + ')...';
        }
        // 2. Delete ALL caches
        if ('caches' in window) {
            const names = await caches.keys();
            for (const n of names) { await caches.delete(n); }
            s.textContent = 'Caches cleared (' + names.length + ')...';
        }
        // 3. Clear storage
        sessionStorage.clear();
        localStorage.clear();
        s.textContent = 'All clear! Redirecting...';
    } catch(e) {
        s.textContent = 'Error: ' + e.message + ' — redirecting anyway...';
    }
    // 4. Redirect to login after a moment
    setTimeout(function(){ window.location.href = '/login'; }, 1000);
})();
</script>
</div></body></html>""", headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Clear-Site-Data": '"cache", "storage"',
    })

@app.get("/", response_class=HTMLResponse)
async def get_customer_chat():
    """Serve the customer-facing AI chat page (public — no auth required)"""
    return FileResponse('templates/customer.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/technician", response_class=HTMLResponse)
async def get_technician_dashboard(request: Request):
    """Serve the technician/support dashboard — requires authentication.
    If no valid token, redirect to /login.
    Inlines app.js to bypass service worker cache.
    """
    token = request.cookies.get("auth_token")
    if not token:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    try:
        await auth_manager.validate_token(token)
        # Read HTML template and JS, inline the JS to bypass any service worker cache
        import pathlib
        base = pathlib.Path(__file__).parent
        html = (base / 'templates' / 'dashboard.html').read_text(encoding='utf-8')
        js = (base / 'static' / 'js' / 'app.js').read_text(encoding='utf-8')
        css = (base / 'static' / 'css' / 'style.css').read_text(encoding='utf-8')
        # Inline JS — service worker can't intercept inline scripts
        html = html.replace(
            '<script src="/static/js/app.js"></script>',
            f'<script>\n{js}\n</script>'
        )
        # Inline CSS — service worker can't intercept inline styles
        html = html.replace(
            '<link rel="stylesheet" href="/static/css/style.css">',
            f'<style>\n{css}\n</style>'
        )
        return HTMLResponse(content=html, headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Clear-Site-Data": '"cache", "storage"',
        })
    except Exception:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)

@app.post("/api/connect")
async def api_connect_to_server(connection: ServerConnection, request: Request):
    """Connect to a Dell server using Redfish API — requires authentication.
    Each authenticated session gets its own agent (per-session connection management).
    """
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    ip = request.client.host if request.client else "?"
    try:
        # Get actual values from UI fields
        host = _validate_host(connection.get_host())
        username = connection.get_username()
        password = connection.get_password()
        port = connection.get_port()
        
        _audit("CONNECT_ATTEMPT", ip=ip, user=user.get("username", "?"), detail=f"host={host}")
        
        # Validate connection parameters
        if not host or not username or not password:
            raise HTTPException(status_code=400, detail="Host, username, and password are required")
        
        # Validate host format
        if not host.strip():
            raise HTTPException(status_code=400, detail="Host cannot be empty")
        
        # Validate host is not localhost or invalid (skip in demo mode)
        if (not app_config or not app_config.demo_mode) and host.strip().lower() in ['localhost', '127.0.0.1', '0.0.0.0']:
            raise HTTPException(status_code=400, detail="Invalid host: Cannot connect to localhost")
        
        # Validate port
        if port < 1 or port > 65535:
            raise HTTPException(status_code=400, detail="Port must be between 1 and 65535")
        
        # Validate username
        if not username.strip():
            raise HTTPException(status_code=400, detail="Username cannot be empty")
        
        # Validate password
        if not password.strip():
            raise HTTPException(status_code=400, detail="Password cannot be empty")
        
        # Try to validate host connectivity first (skip in demo mode)
        if not app_config or not app_config.demo_mode:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((host, port))
                sock.close()
                
                if result != 0:
                    raise HTTPException(status_code=400, detail=f"Cannot connect to {host}:{port}")
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=400, detail=f"Cannot connect to {host}:{port}")
        
        result = await agent.connect_to_server(
            host=host,
            username=username,
            password=password,
            port=port
        )
        conn.host = host
        
        # Auto-register server in fleet manager
        try:
            server_info = await agent.execute_action(
                action_level=ActionLevel.READ_ONLY,
                command="get_server_info",
                parameters={}
            )
            si = server_info.get("server_info", {})
            fleet_manager.add_server(
                name=si.get("model", host),
                host=host,
                username=username,
                password=password,
                port=port,
                model=si.get("model"),
                service_tag=si.get("service_tag"),
                environment="production",
            )
            logger.info(f"Auto-registered {host} in fleet manager")
        except Exception as e:
            logger.warning(f"Could not auto-register server in fleet: {e}")
        
        return {
            "status": "success",
            "message": "Connected successfully",
            "server_info": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/connect")
async def connect_to_server(connection: ServerConnection):
    """Connect to a Dell server using Redfish API (customer page — shared default connection)"""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        success = await agent.connect_to_server(
            host=connection.get_host(),
            username=connection.get_username(),
            password=connection.get_password(),
            port=connection.get_port()
        )
        
        if success:
            # Auto-register server in fleet manager
            try:
                si_data = await agent.execute_action(
                    action_level=ActionLevel.READ_ONLY,
                    command="get_server_info",
                    parameters={}
                )
                si = si_data.get("server_info", {})
                fleet_manager.add_server(
                    name=si.get("model", connection.get_host()),
                    host=connection.get_host(),
                    username=connection.get_username(),
                    password=connection.get_password(),
                    port=connection.get_port(),
                    model=si.get("model"),
                    service_tag=si.get("service_tag"),
                    environment="production",
                )
            except Exception:
                pass  # Fleet registration is best-effort
            
            return {"status": "success", "message": "Connected to server successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to connect to server")
            
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/disconnect")
async def disconnect_from_server(request: Request):
    """Disconnect from the current server (per-session)"""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        
        if not agent.is_connected():
            return {"status": "success", "message": "Already disconnected"}
        
        server_info = {
            "hostname": agent.current_session.server_host if agent.current_session else "unknown",
            "disconnected_at": datetime.utcnow().isoformat()
        }
        
        await agent.disconnect()
        conn.host = None
        
        return {
            "status": "success",
            "message": "Disconnected from server successfully",
            "server_info": server_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting from server: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/execute")
async def api_execute_action(action_req: AgentActionRequest, request: Request):
    """Execute an agent action based on the specified action level — requires authentication"""
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    # Check permission against action level
    al = action_req.action_level.value if hasattr(action_req.action_level, 'value') else str(action_req.action_level)
    if al not in user.get("permissions", []):
        raise HTTPException(status_code=403, detail=f"Your role does not permit '{al}' actions")
    ip = request.client.host if request.client else "?"
    _audit("EXECUTE", ip=ip, user=user.get("username", "?"), detail=f"{action_req.action} [{al}]")
    try:
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        result = await agent.execute_action(action_req.action_level, action_req.action, action_req.parameters)
        return {
            "status": "success",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action {action_req.action}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/execute")
async def execute_action(request: AgentActionRequest):
    """Execute an agent action based on the specified action level (customer — shared connection)"""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        result = await agent.execute_action(request.action_level, request.action, request.parameters)
        return {"status": "success", "data": result}
        
    except Exception as e:
        logger.error(f"Action execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/troubleshoot")
async def api_troubleshoot_server(request: TroubleshootingTask):
    """Start AI-powered troubleshooting via API"""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        result = await agent.troubleshoot_issue(
            issue_description=request.issue_description,
            action_level=request.action_level
        )
        return {
            "status": "success",
            "troubleshooting": result
        }
    except Exception as e:
        logger.error(f"Troubleshooting error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/troubleshoot")
async def troubleshoot_server(request: TroubleshootingTask):
    """Start AI-powered troubleshooting for a server issue (customer — shared connection)"""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        # Only reconnect if not already connected to this host
        if not agent.is_connected() or (
            agent.current_session and
            agent.current_session.server_host != request.server_info.host
        ):
            await agent.connect_to_server(
                host=request.server_info.host,
                username=request.server_info.username,
                password=request.server_info.password,
                port=request.server_info.port
            )
        
        # Start troubleshooting — returns full analysis report + recommendations
        result = await agent.troubleshoot_issue(
            issue_description=request.issue_description,
            action_level=request.action_level
        )
        
        return {
            "status": "success", 
            "recommendations": result["recommendations"],
            "report": result["report"],
            "collected_data": result["collected_data"],
            "issue": request.issue_description
        }
        
    except Exception as e:
        logger.error(f"Troubleshooting error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Agentic Investigation Endpoint ──────────────────────────────
@app.post("/api/investigate")
async def api_investigate_server(request: TroubleshootingTask, req: Request):
    """Start an agentic AI investigation via API (per-session)"""
    try:
        conn, user = await _get_session_conn(req)
        agent = conn.agent
        agent_brain = conn.brain
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        result = await agent_brain.investigate(
            issue=request.issue_description,
            action_level=request.action_level
        )
        return {
            "status": "success",
            "agentic": True,
            "diagnosis": result.get("diagnosis", {}),
            "reasoning_chain": result.get("reasoning_chain", []),
            "recommendations": result.get("recommendations", []),
            "report": result.get("report", {}),
            "collected_data": result.get("collected_data", {}),
            "issue": request.issue_description,
            "metrics": agent_brain._build_business_metrics(),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Investigation error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/investigate")
async def investigate_server(request: TroubleshootingTask):
    """Start an agentic AI investigation — hypothesis-driven, streaming reasoning chain (customer — shared connection)."""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        agent_brain = conn.brain
        # Only reconnect if not already connected to this host
        if not agent.is_connected() or (
            agent.current_session and
            agent.current_session.server_host != request.server_info.host
        ):
            await agent.connect_to_server(
                host=request.server_info.host,
                username=request.server_info.username,
                password=request.server_info.password,
                port=request.server_info.port
            )

        # Run agentic investigation with timing
        from datetime import datetime, timezone
        t0 = datetime.now(timezone.utc)
        result = await agent_brain.investigate(
            issue=request.issue_description,
            action_level=request.action_level
        )
        t1 = datetime.now(timezone.utc)
        agent_brain._investigation_start = t0
        agent_brain._investigation_end = t1
        agent_brain._last_diagnosis = result.get("diagnosis")
        agent_brain._last_issue = request.issue_description

        return {
            "status": "success",
            "agentic": True,
            "diagnosis": result.get("diagnosis", {}),
            "reasoning_chain": result.get("reasoning_chain", []),
            "recommendations": result.get("recommendations", []),
            "report": result.get("report", {}),
            "collected_data": result.get("collected_data", {}),
            "issue": request.issue_description,
            "metrics": agent_brain._build_business_metrics(),
        }

    except Exception as e:
        logger.error(f"Investigation error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Chat Endpoint ─────────────────────────────────────────────
@app.post("/api/chat")
async def api_chat_with_agent(msg: ChatMessage, request: Request):
    """Multi-turn conversational interface with the AI agent via API (per-session)"""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        agent_brain = conn.brain
        if not agent.is_connected():
            return {
                "status": "error",
                "response": {"type": "error", "message": "Please connect to a server first before chatting with the agent."}
            }
        response = await agent_brain.chat(
            message=msg.message,
            action_level=msg.action_level
        )
        return {
            "status": "success",
            "response": response
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/chat")
async def chat_with_agent(msg: ChatMessage):
    """Multi-turn conversational interface with the AI agent (customer — shared connection)."""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        agent_brain = conn.brain
        if not msg.message or not msg.message.strip():
            return {
                "type": "error",
                "message": "Please type a message. Try asking about server health, temperatures, or describe an issue you're seeing.",
                "chat_history": [],
            }
        
        if not agent.is_connected():
            return {
                "type": "error",
                "message": "Please connect to a server first before chatting with the agent.",
                "chat_history": agent_brain._chat_history[-20:],
            }
        result = await agent_brain.chat(
            message=msg.message,
            action_level=msg.action_level
        )
        return result
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        return {
            "type": "error",
            "message": f"Error: {_sanitize_error(e)}",
            "chat_history": agent_brain._chat_history[-20:] if agent_brain else [],
        }

# ─── Streaming Chat Endpoint (SSE) ─────────────────────────────
@app.post("/api/chat/stream")
async def api_chat_stream(msg: ChatMessage, request: Request):
    """SSE streaming chat via API (per-session)"""
    import asyncio
    
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    agent_brain = conn.brain
    
    async def event_generator():
        try:
            # Send initial event
            yield f"data: {json.dumps({'type': 'start', 'message': 'Starting...'}, ensure_ascii=False)}\n\n"
            
            if not agent.is_connected():
                yield f"data: {json.dumps({'type': 'error', 'message': 'Not connected to server'}, ensure_ascii=False)}\n\n"
                return
            
            # Use agent_brain.chat with streaming callback
            event_queue = asyncio.Queue()
            
            async def stream_cb(event_type, data):
                await event_queue.put({"event": event_type, "data": data})
            
            agent_brain.set_stream_callback(stream_cb)
            
            chat_task = asyncio.create_task(
                agent_brain.chat(message=msg.message, action_level=msg.action_level)
            )
            
            while True:
                if chat_task.done():
                    while not event_queue.empty():
                        event = event_queue.get_nowait()
                        yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    yield f"data: {json.dumps(event, default=str, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {json.dumps({'event': 'heartbeat', 'data': {}}, ensure_ascii=False)}\n\n"
            
            try:
                result = chat_task.result()
                yield f"data: {json.dumps({'event': 'complete', 'data': result}, default=str, ensure_ascii=False)}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'event': 'error', 'data': {'message': str(e)}}, ensure_ascii=False)}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        finally:
            agent_brain.set_stream_callback(None)
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )

@app.post("/chat/stream")
async def chat_stream(msg: ChatMessage):
    """SSE streaming chat — sends live thinking steps as they happen (customer — shared connection)."""
    import asyncio

    conn = await _get_default_conn()
    agent = conn.agent
    agent_brain = conn.brain

    event_queue: asyncio.Queue = asyncio.Queue()

    def safe_json(obj):
        """JSON serializer that handles enums, datetimes, and other non-serializable types."""
        def default(o):
            if isinstance(o, Enum):
                return o.value
            if isinstance(o, (datetime, date)):
                return o.isoformat()
            if hasattr(o, 'to_dict'):
                return o.to_dict()
            if hasattr(o, '__dict__'):
                return o.__dict__
            return str(o)
        return json.dumps(obj, default=default, ensure_ascii=False)

    async def stream_callback(event_type: str, data: dict):
        await event_queue.put({"event": event_type, "data": data})

    async def event_generator():
        # Wire up streaming callback
        agent_brain.set_stream_callback(stream_callback)

        # Start chat in background task
        chat_task = asyncio.create_task(
            agent_brain.chat(message=msg.message, action_level=msg.action_level)
        )

        try:
            while True:
                if chat_task.done():
                    # Drain any remaining events
                    while not event_queue.empty():
                        event = event_queue.get_nowait()
                        yield f"data: {safe_json(event)}\n\n"
                    break
                try:
                    event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                    yield f"data: {safe_json(event)}\n\n"
                except asyncio.TimeoutError:
                    yield f"data: {safe_json({'event': 'heartbeat', 'data': {}})}\n\n"

            # Send final result
            try:
                result = chat_task.result()
                payload = safe_json({'event': 'complete', 'data': result})
                yield f"data: {payload}\n\n"
            except Exception as ser_err:
                logger.error(f"Stream serialization error: {ser_err}")
                yield f"data: {safe_json({'event': 'complete', 'data': {'type': 'error', 'message': str(ser_err)}})}\n\n"

        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {safe_json({'event': 'error', 'data': {'message': str(e)}})}\n\n"
        finally:
            agent_brain.set_stream_callback(None)

    if not msg.message or not msg.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not agent.is_connected():
        return {"type": "error", "message": "Please connect to a server first."}

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/check-idrac")
@app.post("/api/check-idrac")
async def check_idrac(connection: ServerConnection):
    """Pre-connection iDRAC availability check (is the server dead?)"""
    try:
        from integrations.redfish_client import RedfishClient
        host = connection.get_host()
        checker = RedfishClient(
            host=host, username=connection.get_username(),
            password=connection.get_password(), port=connection.get_port(), verify_ssl=False
        )
        result = await checker.check_idrac_availability()
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error(f"iDRAC availability check error: {str(e)}")
        return {"status": "error", "data": {"reachable": False, "error": str(e)}}

# ─── OS-Level SSH Connection ─────────────────────────────────────
@app.post("/api/os/connect")
async def connect_to_os(connection: OSConnection):
    """Connect to server OS via SSH"""
    global ssh_client
    try:
        from integrations.ssh_client import SSHClient
        
        # Disconnect existing SSH connection
        if ssh_client and ssh_client.is_connected():
            await ssh_client.disconnect()
        
        ssh_client = SSHClient(
            host=connection.host,
            username=connection.username,
            password=connection.password,
            port=connection.port,
            key_file=connection.key_file
        )
        
        success = await ssh_client.connect()
        
        if success:
            return {
                "status": "success",
                "message": f"Connected to OS via SSH ({ssh_client.os_type})",
                "os_info": ssh_client.os_info,
                "os_type": ssh_client.os_type,
            }
        else:
            raise HTTPException(status_code=400, detail="SSH connection failed - check credentials and ensure SSH is enabled")
            
    except HTTPException:
        raise
    except ImportError:
        raise HTTPException(status_code=500, detail="paramiko library not installed - SSH unavailable")
    except Exception as e:
        logger.error(f"OS connection error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/os/disconnect")
async def disconnect_from_os():
    """Disconnect SSH connection"""
    global ssh_client
    try:
        if ssh_client:
            await ssh_client.disconnect()
            ssh_client = None
        return {"status": "success", "message": "SSH disconnected"}
    except Exception as e:
        logger.error(f"OS disconnect error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/os/execute")
async def execute_os_command(body: dict, request: Request):
    """Execute an OS-level command via SSH — requires authentication + command whitelist"""
    user = await _get_current_user(request)
    ip = request.client.host if request.client else "?"
    global ssh_client
    try:
        if not ssh_client or not ssh_client.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to OS via SSH")
        
        action = body.get("action", "")
        params = body.get("parameters", {})
        
        # Validate action against whitelist
        if action not in _OS_COMMAND_WHITELIST:
            _audit("OS_CMD_BLOCKED", ip=ip, user=user.get("username", "?"), detail=f"action={action}")
            raise HTTPException(status_code=403, detail=f"OS action '{action}' is not permitted")
        
        # custom_command requires admin role
        if action == "custom_command" and user.get("role") != "admin":
            _audit("OS_CMD_BLOCKED", ip=ip, user=user.get("username", "?"), detail="custom_command by non-admin")
            raise HTTPException(status_code=403, detail="Custom commands require admin role")
        
        _audit("OS_EXECUTE", ip=ip, user=user.get("username", "?"), detail=f"action={action}")
        
        # Map actions to SSH client methods
        os_actions = {
            "os_info": ssh_client.get_os_info,
            "system_resources": ssh_client.get_system_resources,
            "running_processes": lambda: ssh_client.get_running_processes(params.get("top_n", 20)),
            "services": ssh_client.get_services,
            "network_info": ssh_client.get_network_info,
            "os_logs": lambda: ssh_client.get_os_logs(params.get("lines", 100)),
            "storage_info": ssh_client.get_storage_info,
            "installed_packages": ssh_client.get_installed_packages,
            "hardware_info": ssh_client.get_hardware_info,
            "service_status": lambda: ssh_client.check_service_status(params.get("service", "")),
            "restart_service": lambda: ssh_client.restart_service(params.get("service", "")),
            "custom_command": lambda: ssh_client.run_custom_command(params.get("command", "")),
        }
        
        handler = os_actions.get(action)
        if not handler:
            raise HTTPException(status_code=400, detail=f"Unknown OS action: {action}")
        
        result = await handler()
        return {"status": "success", "result": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OS command error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Connection Status API ───────────────────────────────────────
@app.get("/api/connection/status")
async def get_connection_status(request: Request):
    """Get comprehensive connection status for both iDRAC and OS (per-session)"""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        idrac_connected = agent.is_connected() if agent else False
        os_connected = ssh_client.is_connected() if ssh_client else False
        
        status = {
            "idrac": {
                "connected": idrac_connected,
                "host": agent.current_session.server_host if idrac_connected and agent.current_session else None,
                "method": agent.current_session.connection_method if idrac_connected and agent.current_session else None,
                "available_methods": agent.get_available_methods() if idrac_connected else [],
            },
            "os": {
                "connected": os_connected,
                "host": ssh_client.host if os_connected else None,
                "os_type": ssh_client.os_type if os_connected else None,
                "os_info": ssh_client.os_info if os_connected else {},
            },
            "mode": "combined" if (idrac_connected and os_connected) else "idrac_only" if idrac_connected else "os_only" if os_connected else "disconnected",
            "features": _get_available_features(idrac_connected, os_connected),
        }
        
        return {"status": "success", "connection": status}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection status error: {e}")
        return {"status": "success", "connection": {
            "idrac": {"connected": False},
            "os": {"connected": False},
            "mode": "disconnected",
            "features": _get_available_features(False, False)
        }}

def _get_available_features(idrac: bool, os: bool) -> Dict[str, Any]:
    """Return feature availability matrix based on connection mode"""
    return {
        # Hardware info - iDRAC primary, OS can supplement
        "server_info": {"available": idrac or os, "source": "idrac" if idrac else "os" if os else None},
        "processors": {"available": idrac or os, "source": "idrac" if idrac else "os"},
        "memory": {"available": idrac or os, "source": "idrac" if idrac else "os"},
        "storage_hardware": {"available": idrac, "source": "idrac"},
        "network_hardware": {"available": idrac, "source": "idrac"},
        "temperatures": {"available": idrac, "source": "idrac"},
        "fans": {"available": idrac, "source": "idrac"},
        "power_supplies": {"available": idrac, "source": "idrac"},
        
        # BIOS/Firmware - iDRAC only
        "bios_attributes": {"available": idrac, "source": "idrac"},
        "firmware_inventory": {"available": idrac, "source": "idrac"},
        "bios_configuration": {"available": idrac, "source": "idrac"},
        
        # iDRAC-specific
        "idrac_info": {"available": idrac, "source": "idrac"},
        "idrac_network": {"available": idrac, "source": "idrac"},
        "idrac_users": {"available": idrac, "source": "idrac"},
        "sel_logs": {"available": idrac, "source": "idrac"},
        "lifecycle_logs": {"available": idrac, "source": "idrac"},
        "boot_order": {"available": idrac, "source": "idrac"},
        "tsr_export": {"available": idrac, "source": "idrac"},
        
        # Power control - iDRAC only
        "power_on": {"available": idrac, "source": "idrac"},
        "power_off": {"available": idrac, "source": "idrac"},
        "power_cycle": {"available": idrac, "source": "idrac"},
        "graceful_shutdown": {"available": idrac or os, "source": "idrac" if idrac else "os"},
        
        # OS-level features - OS (SSH) only
        "os_info": {"available": os, "source": "os"},
        "running_processes": {"available": os, "source": "os"},
        "services": {"available": os, "source": "os"},
        "os_logs": {"available": os, "source": "os"},
        "disk_usage": {"available": os, "source": "os"},
        "os_network": {"available": os, "source": "os"},
        "installed_packages": {"available": os, "source": "os"},
        "custom_commands": {"available": os, "source": "os"},
        
        # Combined features - best with both
        "health_check": {"available": idrac, "source": "idrac", "enhanced_with_os": os},
        "ai_investigation": {"available": idrac, "source": "idrac", "enhanced_with_os": os},
        "full_diagnostics": {"available": idrac and os, "source": "combined"},
    }

@app.get("/api/health")
async def api_health_check():
    """API health check — validates session manager and dependencies."""
    checks = {}
    overall = "healthy"
    
    # Core session manager
    checks["session_manager"] = "ok" if session_mgr else "not_initialized"
    if not session_mgr:
        overall = "degraded"
    
    # Default connection status
    if session_mgr:
        default_conn = await _get_default_conn()
        checks["default_idrac_connected"] = default_conn.agent.is_connected() if default_conn.agent else False
    else:
        checks["default_idrac_connected"] = False
    
    # Active sessions
    if session_mgr:
        checks["active_sessions"] = session_mgr.get_status()["total_sessions"]
    else:
        checks["active_sessions"] = 0
    
    # Auth manager
    checks["auth"] = "ok" if auth_manager else "not_initialized"
    active_auth_sessions = len(auth_manager.sessions) if auth_manager else 0
    checks["active_auth_sessions"] = active_auth_sessions
    
    # Fleet manager
    checks["fleet_servers"] = len(fleet_manager.servers) if fleet_manager else 0
    
    # Realtime monitor
    checks["monitoring_active"] = realtime_monitor.monitoring_active if realtime_monitor else False
    
    # Demo mode
    checks["demo_mode"] = app_config.demo_mode if app_config else False
    
    if checks.get("session_manager") != "ok" or checks.get("auth") != "ok":
        overall = "unhealthy"
    
    return {
        "status": overall,
        "agent": "Medi-AI-tor v2.0 (per-session)",
        "checks": checks,
    }

@app.get("/health")
async def health_check():
    """Lightweight health check for load balancers."""
    if not session_mgr or not auth_manager:
        return JSONResponse(status_code=503, content={"status": "unhealthy"})
    return {"status": "healthy"}

# ─── Per-Session Connection Management Admin Endpoints ────────────
@app.get("/api/sessions")
async def list_agent_sessions(request: Request):
    """List all active agent sessions — admin only."""
    user = await _require_role(request, "admin")
    return {"status": "success", "data": session_mgr.get_status()}

@app.delete("/api/sessions/{session_id}")
async def remove_agent_session(session_id: str, request: Request):
    """Force-remove a specific agent session — admin only."""
    user = await _require_role(request, "admin")
    if session_id == "__default__":
        raise HTTPException(status_code=400, detail="Cannot remove the default customer session")
    # Find full session_id by prefix match
    full_sid = None
    for sid in session_mgr.connections:
        if sid.startswith(session_id.rstrip(".")):
            full_sid = sid
            break
    if not full_sid:
        raise HTTPException(status_code=404, detail="Session not found")
    await session_mgr.remove(full_sid)
    return {"status": "success", "message": f"Session {session_id} removed"}

# ─── Prometheus-Compatible Metrics ───────────────────────────
_request_count = defaultdict(int)
_request_latency_sum = defaultdict(float)

class MetricsMiddleware(BaseHTTPMiddleware):
    """Track request count and latency for Prometheus export."""
    async def dispatch(self, request: Request, call_next):
        t0 = time.time()
        response = await call_next(request)
        elapsed = time.time() - t0
        key = f'{request.method} {request.url.path} {response.status_code}'
        _request_count[key] += 1
        _request_latency_sum[key] += elapsed
        return response

app.add_middleware(MetricsMiddleware)

@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus-compatible metrics endpoint (text/plain exposition format)."""
    lines = ["# HELP http_requests_total Total HTTP requests", "# TYPE http_requests_total counter"]
    for key, count in sorted(_request_count.items()):
        method, path, status = key.split(" ", 2)
        lines.append(f'http_requests_total{{method="{method}",path="{path}",status="{status}"}} {count}')
    lines += ["# HELP http_request_duration_seconds_sum Total request latency", "# TYPE http_request_duration_seconds_sum counter"]
    for key, total in sorted(_request_latency_sum.items()):
        method, path, status = key.split(" ", 2)
        lines.append(f'http_request_duration_seconds_sum{{method="{method}",path="{path}",status="{status}"}} {total:.4f}')
    # Application-level metrics
    lines += ["# HELP medi_ai_tor_info Application info", "# TYPE medi_ai_tor_info gauge"]
    lines.append(f'medi_ai_tor_info{{version="2.0",demo_mode="{app_config.demo_mode if app_config else "unknown"}"}} 1')
    lines += ["# HELP medi_ai_tor_fleet_servers Total fleet servers", "# TYPE medi_ai_tor_fleet_servers gauge"]
    lines.append(f"medi_ai_tor_fleet_servers {len(fleet_manager.servers) if fleet_manager else 0}")
    lines += ["# HELP medi_ai_tor_active_sessions Active auth sessions", "# TYPE medi_ai_tor_active_sessions gauge"]
    lines.append(f"medi_ai_tor_active_sessions {len(auth_manager.sessions) if auth_manager else 0}")
    lines += ["# HELP medi_ai_tor_agent_sessions Active agent sessions", "# TYPE medi_ai_tor_agent_sessions gauge"]
    lines.append(f"medi_ai_tor_agent_sessions {session_mgr.get_status()['total_sessions'] if session_mgr else 0}")
    lines += ["# HELP medi_ai_tor_audit_events Total audit events", "# TYPE medi_ai_tor_audit_events counter"]
    lines.append(f"medi_ai_tor_audit_events {len(_audit_log)}")
    from starlette.responses import PlainTextResponse
    return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication — validates auth token from query or cookie"""
    # Authenticate before accepting
    token = websocket.query_params.get("token") or websocket.cookies.get("auth_token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    try:
        ws_user = await auth_manager.validate_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    await websocket.accept()
    _audit("WS_CONNECT", user=ws_user.get("username", "?"))
    
    # Resolve per-session agent
    sid = ws_user.get("session_id", ws_user.get("username", "anonymous"))
    ws_conn = await session_mgr.get_or_create(sid, ws_user.get("username", "anonymous"))
    ws_agent = ws_conn.agent
    
    try:
        while True:
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                continue
            
            msg_type = message.get("type", "")
            
            # Process different message types
            if msg_type == "command":
                result = await ws_agent.execute_action(
                    action_level=message["action_level"],
                    command=message["command"],
                    parameters=message.get("parameters", {})
                )
                await websocket.send_text(json.dumps({
                    "type": "response",
                    "data": result
                }, ensure_ascii=False))
            elif msg_type == "troubleshoot":
                recommendations = await ws_agent.troubleshoot_issue(
                    issue_description=message["issue_description"],
                    action_level=message["action_level"]
                )
                await websocket.send_text(json.dumps({
                    "type": "troubleshooting_result",
                    "recommendations": recommendations
                }, ensure_ascii=False))
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": _sanitize_error(e)
        }, ensure_ascii=False))

# ─── Health Scoring Endpoint ───────────────────────────────────────
@app.post("/health-score")
async def calculate_health_score(request: dict):
    """Calculate comprehensive health score for server (customer — shared connection)"""
    try:
        conn = await _get_default_conn()
        agent = conn.agent
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        # Execute health scoring command
        result = await agent.execute_action("check_health_score")
        
        if "health_data" not in result:
            raise HTTPException(status_code=500, detail="Failed to collect health data")
        
        return {
            "status": "success",
            "health_data": result["health_data"]
        }
        
    except Exception as e:
        logger.error(f"Health scoring error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Cache Management Endpoint ───────────────────────────────────────
@app.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        from core.cache_manager import cache_manager
        stats = await cache_manager.get_cache_stats()
        return {
            "status": "success",
            "cache_stats": stats
        }
    except Exception as e:
        logger.error(f"Cache stats error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/cache/clear")
async def clear_cache(pattern: str = "*"):
    """Clear cache entries matching pattern"""
    try:
        from core.cache_manager import cache_manager
        cleared = await cache_manager.invalidate(pattern)
        return {
            "status": "success",
            "cleared_entries": cleared,
            "pattern": pattern
        }
    except Exception as e:
        logger.error(f"Cache clear error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Webhook Management Endpoints ───────────────────────────────────
@app.get("/webhooks")
async def list_webhooks():
    """List all webhook endpoints"""
    try:
        from core.webhook_manager import webhook_manager
        stats = await webhook_manager.get_webhook_stats()
        return {
            "status": "success",
            "webhooks": stats
        }
    except Exception as e:
        logger.error(f"Webhook list error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/webhooks/test")
async def test_webhook(webhook_id: str):
    """Test a webhook endpoint"""
    try:
        from core.webhook_manager import webhook_manager, WebhookPayload, WebhookEvent
        
        # Create test payload
        payload = WebhookPayload(
            event_type="test",
            timestamp=datetime.utcnow(),
            server_info={"hostname": "test-server"},
            data={"message": "Test webhook from Medi-AI-tor"},
            severity="info"
        )
        
        success = await webhook_manager.send_webhook(webhook_id, payload)
        
        return {
            "status": "success" if success else "failed",
            "webhook_id": webhook_id,
            "test_result": success
        }
    except Exception as e:
        logger.error(f"Webhook test error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Predictive Analytics Endpoint ───────────────────────────────────
@app.post("/predictive-analysis")
async def run_predictive_analysis(request: dict):
    """Run predictive analytics on server data"""
    try:
        from core.predictive_analytics import predictive_analytics
        
        # In a real implementation, you'd collect historical data
        # For demo, we'll use sample data
        server_data = request.get("server_data", {})
        
        report = await predictive_analytics.generate_predictive_report(server_data)
        
        return {
            "status": "success",
            "predictive_report": report
        }
    except Exception as e:
        logger.error(f"Predictive analysis error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Health Monitoring Endpoints ───────────────────────────────────
@app.post("/monitoring/start")
async def start_health_monitoring(request: Request):
    """Start automated health monitoring + real-time metrics collection"""
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    _audit("MONITORING_START", user=user.get("username", "?"))
    try:
        from core.health_monitor import health_monitor
        
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        # Set server info and client for health_monitor
        server_info = {
            "hostname": agent.current_session.server_host if agent.current_session else "unknown",
            "connected_at": datetime.now().isoformat()
        }
        health_monitor.set_server_info(server_info, agent.redfish_client)
        await health_monitor.start_monitoring()
        
        # Also start realtime_monitor for WebSocket metric streaming
        await realtime_monitor.start_monitoring(agent.redfish_client, interval=30)
        
        return {
            "status": "success",
            "message": "Health monitoring started"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Monitoring start error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/monitoring/stop")
async def stop_health_monitoring(request: Request):
    """Stop automated health monitoring"""
    user = await _get_current_user(request)
    _audit("MONITORING_STOP", user=user.get("username", "?"))
    try:
        from core.health_monitor import health_monitor
        await health_monitor.stop_monitoring()
        await realtime_monitor.stop_monitoring()
        
        return {
            "status": "success",
            "message": "Health monitoring stopped"
        }
    except Exception as e:
        logger.error(f"Monitoring stop error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/monitoring/status")
async def get_monitoring_status():
    """Get health monitoring status"""
    try:
        from core.health_monitor import health_monitor
        status = health_monitor.get_monitoring_status()
        
        return {
            "status": "success",
            "monitoring_status": status
        }
    except Exception as e:
        logger.error(f"Monitoring status error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/monitoring/alerts")
async def get_health_alerts(severity: Optional[str] = None):
    """Get health alerts"""
    try:
        from core.health_monitor import health_monitor, AlertSeverity
        
        alert_severity = None
        if severity:
            try:
                alert_severity = AlertSeverity(severity.lower())
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid severity: {severity}")
        
        alerts = health_monitor.get_active_alerts(alert_severity)
        
        return {
            "status": "success",
            "alerts": [
                {
                    "id": alert.id,
                    "timestamp": alert.timestamp.isoformat(),
                    "severity": alert.severity.value,
                    "component": alert.component,
                    "message": alert.message,
                    "data": alert.data,
                    "acknowledged": alert.acknowledged,
                    "acknowledged_by": alert.acknowledged_by,
                    "acknowledged_at": alert.acknowledged_at.isoformat() if alert.acknowledged_at else None
                }
                for alert in alerts
            ]
        }
    except Exception as e:
        logger.error(f"Alerts error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/monitoring/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str, request: dict):
    """Acknowledge a health alert"""
    try:
        from core.health_monitor import health_monitor
        
        acknowledged_by = request.get("acknowledged_by", "unknown")
        success = health_monitor.acknowledge_alert(alert_id, acknowledged_by)
        
        if not success:
            raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
        
        return {
            "status": "success",
            "message": f"Alert {alert_id} acknowledged"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Alert acknowledge error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/fleet", response_class=HTMLResponse)
async def get_fleet_dashboard():
    """Serve the fleet management dashboard"""
    return FileResponse('templates/fleet.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/api/fleet/overview")
async def get_fleet_overview(request: Request):
    """Get fleet overview data"""
    user = await _get_current_user(request)
    try:
        overview = fleet_manager.get_fleet_overview()
        return {
            "status": "success",
            "data": overview
        }
    except Exception as e:
        logger.error(f"Error getting fleet overview: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/servers")
async def add_fleet_server(server_data: dict, request: Request):
    """Add a new server to the fleet"""
    user = await _get_current_user(request)
    try:
        name = (server_data.get('name') or '').strip()
        host = (server_data.get('host') or '').strip()
        username = (server_data.get('username') or '').strip()
        password = server_data.get('password') or ''
        
        if not name:
            raise HTTPException(status_code=400, detail="Server name is required")
        if not host:
            raise HTTPException(status_code=400, detail="Host is required")
        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password are required")
        
        host = _validate_host(host)
        
        server_id = fleet_manager.add_server(
            name=name,
            host=host,
            username=username,
            password=password,
            port=server_data.get('port', 443),
            model=server_data.get('model'),
            service_tag=server_data.get('service_tag'),
            location=server_data.get('location'),
            environment=server_data.get('environment'),
            tags=server_data.get('tags', []),
            notes=server_data.get('notes')
        )
        
        return {
            "status": "success",
            "server_id": server_id,
            "message": "Server added successfully"
        }
    except Exception as e:
        logger.error(f"Error adding server to fleet: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/servers/{server_id}/connect")
async def connect_fleet_server(server_id: str, request: Request):
    """Connect to a specific server in the fleet"""
    user = await _get_current_user(request)
    try:
        success = await fleet_manager.connect_server(server_id)
        
        return {
            "status": "success" if success else "error",
            "message": "Connected successfully" if success else "Connection failed"
        }
    except Exception as e:
        logger.error(f"Error connecting to server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/servers/{server_id}/disconnect")
async def disconnect_fleet_server(server_id: str, request: Request):
    """Disconnect from a specific server in the fleet"""
    user = await _get_current_user(request)
    try:
        success = await fleet_manager.disconnect_server(server_id)
        
        return {
            "status": "success" if success else "error",
            "message": "Disconnected successfully" if success else "Disconnection failed"
        }
    except Exception as e:
        logger.error(f"Error disconnecting from server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/connect-all")
async def connect_all_fleet_servers(request: Request):
    """Connect to all servers in the fleet"""
    user = await _get_current_user(request)
    try:
        results = await fleet_manager.connect_all_servers()
        
        return {
            "status": "success",
            "results": results,
            "message": f"Connected to {sum(results.values())} of {len(results)} servers"
        }
    except Exception as e:
        logger.error(f"Error connecting to all servers: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/disconnect-all")
async def disconnect_all_fleet_servers(request: Request):
    """Disconnect from all servers in the fleet"""
    user = await _get_current_user(request)
    try:
        results = await fleet_manager.disconnect_all_servers()
        
        return {
            "status": "success",
            "results": results,
            "message": f"Disconnected from {sum(results.values())} of {len(results)} servers"
        }
    except Exception as e:
        logger.error(f"Error disconnecting from all servers: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/api/fleet/servers/{server_id}")
async def get_fleet_server(server_id: str, request: Request):
    """Get details for a specific server"""
    user = await _get_current_user(request)
    try:
        server = fleet_manager.get_server(server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        
        server_data = server.to_dict() if hasattr(server, 'to_dict') else server
        return {
            "status": "success",
            "server": server_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.put("/api/fleet/servers/{server_id}")
async def update_fleet_server(server_id: str, server_data: dict, request: Request):
    """Update a server in the fleet"""
    user = await _get_current_user(request)
    try:
        success = fleet_manager.update_server(server_id, **server_data)
        
        if success:
            return {
                "status": "success",
                "message": "Server updated successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Server not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.delete("/api/fleet/servers/{server_id}")
async def delete_fleet_server(server_id: str, request: Request):
    """Delete a server from the fleet"""
    user = await _get_current_user(request)
    try:
        success = fleet_manager.delete_server(server_id)
        
        if success:
            return {
                "status": "success",
                "message": "Server deleted successfully"
            }
        else:
            raise HTTPException(status_code=404, detail="Server not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/servers/{server_id}/diagnostics")
async def run_server_diagnostics(server_id: str, request: Request):
    """Run diagnostics on a specific server"""
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    try:
        server = fleet_manager.get_server(server_id)
        if not server:
            raise HTTPException(status_code=404, detail="Server not found")
        
        # Check if server is connected
        if server_id not in fleet_manager.active_connections:
            raise HTTPException(status_code=400, detail="Server not connected")
        
        # Run diagnostics using the agent
        if agent and agent.is_connected():
            # Switch to this server if needed
            if agent.redfish_client.host != server.host:
                # Reconnect to the target server
                success = await agent.redfish_client.connect(
                    host=server.host,
                    username=server.username,
                    password=server.password,
                    port=server.port
                )
                if not success:
                    raise HTTPException(status_code=400, detail="Failed to connect to server for diagnostics")
            
            # Run investigation
            investigation_result = await agent.investigate("Run comprehensive system diagnostics")
            
            return {
                "status": "success",
                "server_name": server.name,
                "diagnostics": investigation_result,
                "message": f"Diagnostics completed for {server.name}"
            }
        else:
            raise HTTPException(status_code=503, detail="Agent not available")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Diagnostics error for server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/health-check")
async def run_fleet_health_check(request: Request):
    """Run health check on all connected servers"""
    user = await _get_current_user(request)
    try:
        results = await fleet_manager.run_fleet_health_check()
        
        return {
            "status": "success",
            "data": results,
            "message": f"Health check completed for {results['connected_servers']} servers"
        }
    except Exception as e:
        logger.error(f"Fleet health check error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/alerts/{alert_index}/acknowledge")
async def acknowledge_fleet_alert(alert_index: int, request: Request, body: dict = None):
    """Acknowledge a fleet alert"""
    user = await _get_current_user(request)
    try:
        alerts = fleet_manager.get_recent_alerts(hours=168, limit=1000)
        if 0 <= alert_index < len(alerts):
            alerts[alert_index]["acknowledged"] = True
            alerts[alert_index]["acknowledged_by"] = (body or {}).get("acknowledged_by", user.get("username", "user"))
            alerts[alert_index]["acknowledged_at"] = datetime.now().isoformat()
            return {"status": "success", "message": "Alert acknowledged"}
        raise HTTPException(status_code=404, detail="Alert not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error acknowledging fleet alert: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/alerts/clear")
async def clear_fleet_alerts(request: Request, body: dict = None):
    """Clear resolved/acknowledged fleet alerts"""
    user = await _get_current_user(request)
    try:
        before = len(fleet_manager.alerts)
        fleet_manager.alerts = [a for a in fleet_manager.alerts if not a.get("acknowledged")]
        after = len(fleet_manager.alerts)
        return {"status": "success", "cleared": before - after, "remaining": after}
    except Exception as e:
        logger.error(f"Error clearing fleet alerts: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/api/fleet/alerts")
async def get_fleet_alerts(request: Request, hours: int = Query(default=24, ge=1, le=720), limit: int = Query(default=100, ge=1, le=1000)):
    """Get recent alerts from all servers"""
    user = await _get_current_user(request)
    try:
        alerts = fleet_manager.get_recent_alerts(hours, limit)
        
        return {
            "status": "success",
            "alerts": alerts,
            "total": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error getting fleet alerts: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/mobile", response_class=HTMLResponse)
async def get_mobile_dashboard():
    """Serve the mobile-responsive dashboard"""
    return FileResponse('templates/mobile.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/monitoring", response_class=HTMLResponse)
async def get_realtime_dashboard(request: Request):
    """Serve the real-time monitoring dashboard — inlines JS to bypass SW cache."""
    # Check auth — redirect to login if no token
    token = request.cookies.get("auth_token")
    if not token:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    try:
        await auth_manager.validate_token(token)
    except Exception:
        from starlette.responses import RedirectResponse
        return RedirectResponse(url="/login", status_code=302)
    
    import pathlib
    base = pathlib.Path(__file__).parent
    html = (base / 'templates' / 'realtime.html').read_text(encoding='utf-8')
    rt_js = (base / 'static' / 'js' / 'realtime.js').read_text(encoding='utf-8')
    rt_css = (base / 'static' / 'css' / 'realtime.css').read_text(encoding='utf-8')
    html = html.replace('<script src="/static/js/realtime.js"></script>', f'<script>\n{rt_js}\n</script>')
    html = html.replace('<link rel="stylesheet" href="/static/css/realtime.css">', f'<style>\n{rt_css}\n</style>')
    return HTMLResponse(content=html, headers={
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Clear-Site-Data": '"cache", "storage"',
    })

@app.websocket("/ws/monitoring")
async def websocket_monitoring(websocket: WebSocket):
    """WebSocket endpoint for real-time monitoring — requires auth token"""
    token = websocket.query_params.get("token") or websocket.cookies.get("auth_token")
    if not token:
        await websocket.close(code=4001, reason="Authentication required")
        return
    try:
        ws_user = await auth_manager.validate_token(token)
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    await websocket.accept()
    
    # Resolve per-session agent
    sid = ws_user.get("session_id", ws_user.get("username", "anonymous"))
    ws_conn = await session_mgr.get_or_create(sid, ws_user.get("username", "anonymous"))
    ws_agent = ws_conn.agent
    
    # Add connection to monitor
    realtime_monitor.add_websocket_connection(websocket)
    
    try:
        # Start monitoring if not already running
        if not realtime_monitor.monitoring_active and ws_agent.is_connected():
            await realtime_monitor.start_monitoring(ws_agent.redfish_client)
        
        # Send initial metrics as metrics_update so frontend handles it uniformly
        current_metrics = realtime_monitor.get_current_metrics()
        await websocket.send_text(json.dumps({
            "type": "metrics_update",
            "timestamp": current_metrics.get("timestamp", datetime.now().isoformat()),
            "metrics": current_metrics.get("metrics", {}),
            "monitoring_active": current_metrics.get("monitoring_active", False)
        }, ensure_ascii=False))
        
        # Keep connection alive and handle messages
        while True:
            try:
                message = await websocket.receive_text()
                try:
                    data = json.loads(message)
                except json.JSONDecodeError:
                    await websocket.send_text(json.dumps({"type": "error", "message": "Invalid JSON"}))
                    continue
                
                # Handle client messages
                if data.get("action") == "start_monitoring":
                    if ws_agent.is_connected():
                        await realtime_monitor.start_monitoring(ws_agent.redfish_client)
                        await websocket.send_text(json.dumps({
                            "type": "monitoring_started",
                            "data": {"status": "success"}
                        }, ensure_ascii=False))
                    else:
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "data": {"message": "Not connected to server"}
                        }, ensure_ascii=False))
                elif data.get("action") == "stop_monitoring":
                    await realtime_monitor.stop_monitoring()
                    await websocket.send_text(json.dumps({
                        "type": "monitoring_stopped",
                        "data": {"status": "success"}
                    }, ensure_ascii=False))
                elif data.get("action") == "get_metrics":
                    metrics = realtime_monitor.get_current_metrics()
                    await websocket.send_text(json.dumps({
                        "type": "metrics_update",
                        "data": metrics
                    }, ensure_ascii=False))
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"WebSocket message error: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "data": {"message": _sanitize_error(e)}
                }, ensure_ascii=False))
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        # Remove connection from monitor
        realtime_monitor.remove_websocket_connection(websocket)

@app.get("/monitoring/metrics")
async def get_current_metrics():
    """Get current snapshot of all metrics"""
    try:
        metrics = realtime_monitor.get_current_metrics()
        return {
            "status": "success",
            "data": metrics
        }
    except Exception as e:
        logger.error(f"Metrics error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/monitoring/metrics/{metric_name}/history")
async def get_metric_history(metric_name: str, minutes: int = Query(default=60, ge=1, le=1440)):
    """Get historical data for a specific metric"""
    try:
        history = realtime_monitor.get_metric_history(metric_name, minutes)
        return {
            "status": "success",
            "data": {
                "metric": metric_name,
                "minutes": minutes,
                "history": history
            }
        }
    except Exception as e:
        logger.error(f"Metric history error: {str(e)}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Fleet Group Management Endpoints ──────────────────────────────
@app.get("/api/fleet/groups")
async def get_fleet_groups(request: Request):
    """Get all server groups"""
    user = await _get_current_user(request)
    try:
        groups = {}
        for name, group in fleet_manager.server_groups.items():
            groups[name] = {
                "name": group.name,
                "description": group.description,
                "server_count": len(group.server_ids),
                "server_ids": list(group.server_ids),
                "created_at": group.created_at.isoformat() if group.created_at else None,
                "tags": list(group.tags) if group.tags else []
            }
        return {"status": "success", "groups": groups}
    except Exception as e:
        logger.error(f"Error getting fleet groups: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/groups")
async def create_fleet_group(group_data: dict, request: Request):
    """Create a new server group"""
    user = await _get_current_user(request)
    try:
        name = group_data.get("name")
        description = group_data.get("description", "")
        server_ids = group_data.get("server_ids", [])
        
        if not name:
            raise HTTPException(status_code=400, detail="Group name is required")
        
        group_name = fleet_manager.create_group(name, description, server_ids)
        return {
            "status": "success",
            "group_name": group_name,
            "message": f"Group '{name}' created successfully"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error creating fleet group: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.delete("/api/fleet/groups/{group_name}")
async def delete_fleet_group(group_name: str, request: Request):
    """Delete a server group"""
    user = await _get_current_user(request)
    try:
        success = fleet_manager.delete_group(group_name)
        if success:
            return {"status": "success", "message": f"Group '{group_name}' deleted successfully"}
        else:
            raise HTTPException(status_code=400, detail="Cannot delete default groups or group not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting fleet group: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/groups/{group_name}/servers/{server_id}")
async def add_server_to_group(group_name: str, server_id: str, request: Request):
    """Add a server to a group"""
    user = await _get_current_user(request)
    try:
        success = fleet_manager.add_server_to_group(server_id, group_name)
        if success:
            return {"status": "success", "message": f"Server added to group '{group_name}'"}
        else:
            raise HTTPException(status_code=404, detail="Server or group not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding server to group: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.delete("/api/fleet/groups/{group_name}/servers/{server_id}")
async def remove_server_from_group(group_name: str, server_id: str, request: Request):
    """Remove a server from a group"""
    user = await _get_current_user(request)
    try:
        success = fleet_manager.remove_server_from_group(server_id, group_name)
        if success:
            return {"status": "success", "message": f"Server removed from group '{group_name}'"}
        else:
            raise HTTPException(status_code=404, detail="Server or group not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing server from group: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Fleet Analytics Endpoints ──────────────────────────────
@app.get("/api/fleet/analytics")
async def get_fleet_analytics(request: Request, time_range: str = "24h", metric: str = "health"):
    """Get fleet analytics data"""
    user = await _get_current_user(request)
    try:
        overview = fleet_manager.get_fleet_overview()
        alerts = fleet_manager.get_recent_alerts(hours=168 if time_range == "week" else 720 if time_range == "month" else 24)
        
        # Build analytics data
        analytics = {
            "time_range": time_range,
            "metric": metric,
            "summary": {
                "total_servers": overview["total_servers"],
                "avg_health": overview["average_health_score"],
                "total_alerts": overview["total_alerts"],
                "online_percentage": round((overview["online_servers"] / max(overview["total_servers"], 1)) * 100, 1),
                "uptime_estimate": 99.9 if overview["online_servers"] == overview["total_servers"] else round((overview["online_servers"] / max(overview["total_servers"], 1)) * 100, 1)
            },
            "health_distribution": {
                "excellent": len([s for s in fleet_manager.servers.values() if s.health_score >= 90]),
                "good": len([s for s in fleet_manager.servers.values() if 70 <= s.health_score < 90]),
                "warning": len([s for s in fleet_manager.servers.values() if 50 <= s.health_score < 70]),
                "critical": len([s for s in fleet_manager.servers.values() if 0 < s.health_score < 50])
            },
            "environments": overview["environments"],
            "recent_alerts": [
                {
                    "server_name": a.get("server_name", "Unknown"),
                    "type": a.get("type", "info"),
                    "message": a.get("message", ""),
                    "timestamp": a["timestamp"].isoformat() if isinstance(a.get("timestamp"), datetime) else str(a.get("timestamp", ""))
                }
                for a in alerts[:50]
            ]
        }
        
        return {"status": "success", "data": analytics}
    except Exception as e:
        logger.error(f"Error getting fleet analytics: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.post("/api/fleet/analytics/report")
async def generate_fleet_report(request: Request, report_config: dict = None):
    """Generate a fleet analytics report"""
    user = await _get_current_user(request)
    report_config = report_config or {}
    try:
        overview = fleet_manager.get_fleet_overview()
        alerts = fleet_manager.get_recent_alerts(hours=168)
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "fleet_summary": {
                "total_servers": overview["total_servers"],
                "online_servers": overview["online_servers"],
                "offline_servers": overview["offline_servers"],
                "error_servers": overview["error_servers"],
                "average_health_score": overview["average_health_score"],
                "total_alerts": overview["total_alerts"],
            },
            "server_details": [
                {
                    "name": s.name,
                    "host": s.host,
                    "status": s.status.value,
                    "health_score": s.health_score,
                    "environment": s.environment,
                    "alert_count": s.alert_count,
                    "last_seen": s.last_seen.isoformat() if s.last_seen else None
                }
                for s in fleet_manager.servers.values()
            ],
            "recent_alerts": [
                {
                    "server_name": a.get("server_name", "Unknown"),
                    "type": a.get("type", "info"),
                    "message": a.get("message", ""),
                    "timestamp": a["timestamp"].isoformat() if isinstance(a.get("timestamp"), datetime) else str(a.get("timestamp", ""))
                }
                for a in alerts[:100]
            ],
            "recommendations": []
        }
        
        # Generate recommendations
        if overview["error_servers"] > 0:
            report["recommendations"].append({
                "priority": "high",
                "message": f"{overview['error_servers']} server(s) are in error state and need attention"
            })
        if overview["average_health_score"] < 70:
            report["recommendations"].append({
                "priority": "medium",
                "message": f"Average fleet health score is {overview['average_health_score']}% - consider investigating low-scoring servers"
            })
        if overview["total_alerts"] > 10:
            report["recommendations"].append({
                "priority": "medium",
                "message": f"High alert count ({overview['total_alerts']}) - review and resolve outstanding alerts"
            })
        
        return {"status": "success", "report": report}
    except Exception as e:
        logger.error(f"Error generating fleet report: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Export Endpoints ──────────────────────────────
@app.get("/api/fleet/export/servers")
async def export_fleet_servers(request: Request, format: str = "json"):
    """Export fleet servers data"""
    user = await _get_current_user(request)
    try:
        servers_data = []
        for server in fleet_manager.servers.values():
            servers_data.append({
                "name": server.name,
                "host": server.host,
                "port": server.port,
                "status": server.status.value,
                "health_score": server.health_score,
                "environment": server.environment or "",
                "location": server.location or "",
                "tags": ",".join(server.tags) if server.tags else "",
                "alert_count": server.alert_count,
                "last_seen": server.last_seen.isoformat() if server.last_seen else ""
            })
        
        if format == "csv":
            import io
            output = io.StringIO()
            if servers_data:
                headers = servers_data[0].keys()
                output.write(",".join(headers) + "\n")
                for row in servers_data:
                    output.write(",".join(str(v) for v in row.values()) + "\n")
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=fleet_servers.csv"}
            )
        
        return {"status": "success", "data": servers_data}
    except Exception as e:
        logger.error(f"Error exporting servers: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/api/fleet/export/alerts")
async def export_fleet_alerts(request: Request, format: str = "json", hours: int = Query(default=24, ge=1, le=720)):
    """Export fleet alerts data"""
    user = await _get_current_user(request)
    try:
        alerts = fleet_manager.get_recent_alerts(hours=hours, limit=1000)
        alerts_data = [
            {
                "server_name": a.get("server_name", "Unknown"),
                "type": a.get("type", "info"),
                "metric": a.get("metric", ""),
                "message": a.get("message", ""),
                "timestamp": a["timestamp"].isoformat() if isinstance(a.get("timestamp"), datetime) else str(a.get("timestamp", ""))
            }
            for a in alerts
        ]
        
        if format == "csv":
            import io
            output = io.StringIO()
            if alerts_data:
                headers = alerts_data[0].keys()
                output.write(",".join(headers) + "\n")
                for row in alerts_data:
                    output.write(",".join(str(v) for v in row.values()) + "\n")
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=fleet_alerts.csv"}
            )
        
        return {"status": "success", "data": alerts_data}
    except Exception as e:
        logger.error(f"Error exporting alerts: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Server Snapshot / Quick Status Endpoint ─────────────────────
# Stores snapshots in memory for timeline
_health_snapshots = []

@app.get("/api/server/snapshot")
async def get_server_snapshot(request: Request):
    """Get a comprehensive snapshot of current server status - used for timeline/history"""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "server": {
                "host": agent.current_session.server_host if agent.current_session else "unknown",
            },
            "thermal": {},
            "power": {},
            "health": {},
        }
        
        # Collect thermal
        try:
            temps = await agent.execute_action(ActionLevel.READ_ONLY, "get_temperature_sensors", {})
            snapshot["thermal"] = temps
        except Exception as e:
            logger.warning(f"Snapshot: thermal data unavailable: {e}")
        
        # Collect power
        try:
            power = await agent.execute_action(ActionLevel.READ_ONLY, "get_power_supplies", {})
            snapshot["power"] = power
        except Exception as e:
            logger.warning(f"Snapshot: power data unavailable: {e}")
        
        # Collect health
        try:
            health = await agent.execute_action(ActionLevel.READ_ONLY, "health_check", {})
            snapshot["health"] = health
        except Exception as e:
            logger.warning(f"Snapshot: health data unavailable: {e}")
        
        # Store snapshot
        _health_snapshots.append(snapshot)
        if len(_health_snapshots) > 100:
            _health_snapshots.pop(0)
        
        return {"status": "success", "snapshot": snapshot}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

@app.get("/api/server/timeline")
async def get_server_timeline(limit: int = Query(default=50, ge=1, le=200)):
    """Get health snapshot timeline"""
    try:
        return {
            "status": "success",
            "timeline": _health_snapshots[-limit:],
            "total": len(_health_snapshots)
        }
    except Exception as e:
        logger.error(f"Timeline error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Quick Server Status (lightweight) ─────────────────────────
@app.get("/api/server/quick-status")
async def get_quick_status(request: Request):
    """Lightweight server status — just the essentials for dashboard header.
    Uses cached data when available, only fetches system info if needed."""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        if not agent.is_connected():
            return {"status": "disconnected", "connected": False}
        
        host = agent.current_session.server_host if agent.current_session else "unknown"
        
        # Fetch server info and health in PARALLEL (not sequential)
        result = {"connected": True, "host": host}
        try:
            si_task = agent.execute_action(ActionLevel.READ_ONLY, "get_server_info", {})
            health_task = agent.execute_action(ActionLevel.READ_ONLY, "health_check", {})
            si, health = await asyncio.gather(si_task, health_task, return_exceptions=True)
            
            # Process server info
            if not isinstance(si, Exception):
                info = si.get("server_info", {})
                result.update({
                    "model": info.get("model", "Unknown"),
                    "service_tag": info.get("service_tag", ""),
                    "power_state": info.get("power_state", "Unknown"),
                    "bios_version": info.get("bios_version", ""),
                    "idrac_version": info.get("idrac_version", ""),
                    "cpu_model": info.get("cpu_model", ""),
                    "cpu_count": info.get("cpu_count", 0),
                    "total_memory_gb": info.get("total_memory_gb", 0),
                })
            
            # Process health
            if not isinstance(health, Exception):
                hs = health.get("health_status", {})
                overall = hs.get("overall_status", "unknown")
                if hasattr(overall, 'value'):
                    overall = overall.value
                result["health"] = str(overall)
                result["critical_count"] = len(hs.get("critical_issues", []))
                result["warning_count"] = len(hs.get("warnings", []))
        except Exception as e:
            result["error"] = str(e)
        
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Quick status error: {e}")
        return {"status": "error", "error": _sanitize_error(e), "connected": False}

# ─── Batch Execute (multiple commands in one request) ──────────
@app.post("/api/execute/batch")
async def batch_execute(body: dict, request: Request):
    """Execute multiple commands in a single request — requires authentication"""
    conn, user = await _get_session_conn(request)
    agent = conn.agent
    ip = request.client.host if request.client else "?"
    _audit("BATCH_EXECUTE", ip=ip, user=user.get("username", "?"), detail=f"{len(body.get('commands', []))} cmds")
    try:
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        commands = body.get("commands", [])
        if not commands or len(commands) > 20:
            raise HTTPException(status_code=400, detail="Provide 1-20 commands")
        
        results = {}
        for cmd in commands:
            action = cmd.get("action", "")
            params = cmd.get("parameters", {})
            level = cmd.get("action_level", "read_only")
            try:
                al = ActionLevel(level) if isinstance(level, str) else level
                result = await agent.execute_action(al, action, params)
                results[action] = {"status": "success", "result": result}
            except Exception as e:
                results[action] = {"status": "error", "error": _sanitize_error(e)}
        
        return {"status": "success", "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Batch execute error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Quick Diagnostics Summary ─────────────────────────────────
@app.get("/api/server/diagnostics-summary")
async def get_diagnostics_summary(request: Request):
    """Get a quick one-shot diagnostics summary of the connected server"""
    try:
        conn, user = await _get_session_conn(request)
        agent = conn.agent
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        summary = {
            "timestamp": datetime.now().isoformat(),
            "overall": "unknown",
            "components": {},
            "alerts": [],
            "recommendations": [],
        }
        
        # Get health check
        try:
            health = await agent.execute_action(ActionLevel.READ_ONLY, "health_check", {})
            hs = health.get("health_status", {})
            summary["overall"] = hs.get("overall_status", "unknown")
            summary["components"] = hs.get("components", {})
            for issue in hs.get("critical_issues", [])[:5]:
                summary["alerts"].append({
                    "severity": issue.get("severity", "warning"),
                    "message": issue.get("message", "Unknown issue"),
                    "timestamp": issue.get("timestamp", ""),
                })
        except Exception as e:
            summary["alerts"].append({"severity": "error", "message": f"Health check failed: {e}"})
        
        # Get thermal summary
        try:
            temps = await agent.execute_action(ActionLevel.READ_ONLY, "get_temperature_sensors", {})
            temp_list = temps.get("temperatures", [])
            max_temp = max((t.get("reading_celsius", 0) for t in temp_list), default=0)
            summary["thermal"] = {
                "max_temperature": max_temp,
                "sensor_count": len(temp_list),
                "status": "critical" if max_temp > 85 else "warning" if max_temp > 75 else "ok"
            }
        except Exception as e:
            logger.warning(f"Diagnostics: thermal data unavailable: {e}")
            summary["thermal"] = {"max_temperature": 0, "sensor_count": 0, "status": "unknown"}
        
        # Get power summary
        try:
            power = await agent.execute_action(ActionLevel.READ_ONLY, "get_power_supplies", {})
            psus = power.get("power_supplies", [])
            healthy = sum(1 for p in psus if "OK" in str(p.get("status", "")))
            summary["power"] = {
                "total_psus": len(psus),
                "healthy_psus": healthy,
                "status": "ok" if healthy == len(psus) else "critical" if healthy == 0 else "warning"
            }
        except Exception as e:
            logger.warning(f"Diagnostics: power data unavailable: {e}")
            summary["power"] = {"total_psus": 0, "healthy_psus": 0, "status": "unknown"}
        
        # Generate recommendations
        if summary.get("thermal", {}).get("status") == "critical":
            summary["recommendations"].append("Critical temperature detected. Check airflow and fan operation immediately.")
        if summary.get("power", {}).get("status") != "ok":
            summary["recommendations"].append("Power supply issue detected. Check PSU connections and redundancy.")
        if summary["overall"] == "critical":
            summary["recommendations"].append("Server health is critical. Run full diagnostics and check event logs.")
        if not summary["recommendations"]:
            summary["recommendations"].append("Server appears healthy. No immediate action required.")
        
        return {"status": "success", "summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Diagnostics summary error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

# ─── Server Comparison ──────────────────────────────────────────
@app.post("/api/fleet/compare")
async def compare_fleet_servers(body: dict, request: Request):
    """Compare two or more servers side by side"""
    user = await _get_current_user(request)
    try:
        server_ids = body.get("server_ids", [])
        if len(server_ids) < 2:
            raise HTTPException(status_code=400, detail="Need at least 2 servers to compare")
        
        comparison = {
            "timestamp": datetime.now().isoformat(),
            "servers": []
        }
        
        for sid in server_ids:
            server = fleet_manager.get_server(sid)
            if server:
                server_data = {
                    "id": sid,
                    "name": server.name,
                    "host": server.host,
                    "status": server.status.value,
                    "health_score": server.health_score,
                    "environment": server.environment,
                    "location": server.location,
                    "model": server.model,
                    "service_tag": server.service_tag,
                    "alert_count": server.alert_count,
                    "last_seen": server.last_seen.isoformat() if server.last_seen else None,
                }
                comparison["servers"].append(server_data)
        
        return {"status": "success", "comparison": comparison}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Comparison error: {e}")
        raise HTTPException(status_code=500, detail=_sanitize_error(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
