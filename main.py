#!/usr/bin/env python3
"""
Dell Server AI Agent - Hackathon Project
A lightweight AI agent that acts as an intermediary between Virtual Assistants 
and Dell servers, leveraging Redfish API and RACADM for comprehensive server management.
"""

import asyncio
import logging
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List, Union
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

# main.py (top imports)
from models.server_models import ActionLevel


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Dell Server AI Agent",
    description="AI-powered Dell server management and troubleshooting agent",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize global components
agent = None
agent_brain = None
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
    global agent, agent_brain, automation_engine, multi_server_manager, analytics_engine
    global predictive_analytics, predictive_maintenance, voice_assistant, third_party_api
    global realtime_monitor, health_monitor, webhook_manager, rbac_manager
    
    config = AgentConfig.from_env()
    
    if config.demo_mode:
        logger.info("*** DEMO MODE ENABLED — using simulated server data ***")
    
    # Initialize core components
    agent = DellAIAgent(config)
    realtime_monitor = RealtimeMonitor()
    health_monitor = HealthMonitor()
    webhook_manager = WebhookManager()
    rbac_manager = RBACManager()
    agent_brain = AgentBrain(agent, config)
    predictive_analytics = PredictiveAnalytics(config)
    predictive_maintenance = PredictiveMaintenance(predictive_analytics)
    analytics_engine = AnalyticsEngine()
    automation_engine = AutomationEngine(agent)
    multi_server_manager = MultiServerManager(config)
    
    # Optional components (may not exist)
    try:
        from integrations.voice_assistant import VoiceAssistant
        voice_assistant = VoiceAssistant(agent)
    except ImportError:
        voice_assistant = None
    
    try:
        from api.third_party_api import ThirdPartyAPI
        third_party_api = ThirdPartyAPI(agent)
    except ImportError:
        third_party_api = None
    
    logger.info("Dell AI Agent and all components initialized successfully")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_customer_chat():
    """Serve the customer-facing AI chat page"""
    return FileResponse('templates/customer.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/technician", response_class=HTMLResponse)
async def get_technician_dashboard():
    """Serve the technician/support dashboard"""
    return FileResponse('templates/dashboard.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.post("/api/connect")
async def api_connect_to_server(connection: ServerConnection):
    """Connect to a Dell server using Redfish API"""
    try:
        # Get actual values from UI fields
        host = connection.get_host()
        username = connection.get_username()
        password = connection.get_password()
        port = connection.get_port()
        
        # Validate connection parameters
        if not host or not username or not password:
            raise HTTPException(status_code=400, detail="Host, username, and password are required")
        
        # Validate host format
        if not host.strip():
            raise HTTPException(status_code=400, detail="Host cannot be empty")
        
        # Validate host is not localhost or invalid (skip in demo mode)
        if not agent.config.demo_mode and host.strip().lower() in ['localhost', '127.0.0.1', '0.0.0.0']:
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
        if not agent.config.demo_mode:
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
        return {
            "status": "success",
            "message": "Connected successfully",
            "server_info": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/connect")
async def connect_to_server(connection: ServerConnection):
    """Connect to a Dell server using Redfish API"""
    try:
        success = await agent.connect_to_server(
            host=connection.get_host(),
            username=connection.get_username(),
            password=connection.get_password(),
            port=connection.get_port()
        )
        
        if success:
            return {"status": "success", "message": "Connected to server successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to connect to server")
            
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/disconnect")
async def disconnect_from_server():
    """Disconnect from the current server"""
    try:
        if not agent:
            raise HTTPException(status_code=500, detail="Agent not initialized")
        
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="No active connection")
        
        server_info = {
            "hostname": agent.current_session.server_host if agent.current_session else "unknown",
            "disconnected_at": datetime.utcnow().isoformat()
        }
        
        await agent.disconnect()
        
        return {
            "status": "success",
            "message": "Disconnected from server successfully",
            "server_info": server_info
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error disconnecting from server: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/execute")
async def api_execute_action(request: AgentActionRequest):
    """Execute an agent action based on the specified action level"""
    try:
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        result = await agent.execute_action(request.action_level, request.action, request.parameters)
        return {
            "status": "success",
            "result": result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing action {request.action}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute")
async def execute_action(request: AgentActionRequest):
    """Execute an agent action based on the specified action level"""
    try:
        result = await agent.execute_action(request.action_level, request.action, request.parameters)
        return {"status": "success", "data": result}
        
    except Exception as e:
        logger.error(f"Action execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/troubleshoot")
async def api_troubleshoot_server(request: TroubleshootingTask):
    """Start AI-powered troubleshooting via API"""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/troubleshoot")
async def troubleshoot_server(request: TroubleshootingTask):
    """Start AI-powered troubleshooting for a server issue"""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Agentic Investigation Endpoint ──────────────────────────────
@app.post("/api/investigate")
async def api_investigate_server(request: TroubleshootingTask):
    """Start an agentic AI investigation via API"""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/investigate")
async def investigate_server(request: TroubleshootingTask):
    """Start an agentic AI investigation — hypothesis-driven, streaming reasoning chain."""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Chat Endpoint ─────────────────────────────────────────────
@app.post("/api/chat")
async def api_chat_with_agent(msg: ChatMessage):
    """Multi-turn conversational interface with the AI agent via API"""
    try:
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
    except Exception as e:
        logger.error(f"Chat error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/chat")
async def chat_with_agent(msg: ChatMessage):
    """Multi-turn conversational interface with the AI agent."""
    try:
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
            "message": f"Error: {str(e)}",
            "chat_history": agent_brain._chat_history[-20:] if agent_brain else [],
        }

# ─── Streaming Chat Endpoint (SSE) ─────────────────────────────
@app.post("/api/chat/stream")
async def api_chat_stream(msg: ChatMessage):
    """SSE streaming chat via API"""
    import asyncio
    
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
    """SSE streaming chat — sends live thinking steps as they happen."""
    import asyncio

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/os/execute")
async def execute_os_command(request: dict):
    """Execute an OS-level command via SSH"""
    global ssh_client
    try:
        if not ssh_client or not ssh_client.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to OS via SSH")
        
        action = request.get("action", "")
        params = request.get("parameters", {})
        
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
            raise HTTPException(status_code=400, detail=f"Unknown OS action: {action}. Available: {list(os_actions.keys())}")
        
        result = await handler()
        return {"status": "success", "result": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OS command error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Connection Status API ───────────────────────────────────────
@app.get("/api/connection/status")
async def get_connection_status():
    """Get comprehensive connection status for both iDRAC and OS"""
    try:
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
    """API health check endpoint"""
    return {
        "status": "healthy",
        "agent": "Dell Server AI Agent v1.0.0",
        "demo_mode": agent.config.demo_mode if agent else False,
    }

@app.get("/health")
async def health_check():
    """API health check endpoint"""
    return {
        "status": "healthy",
        "agent": "Dell Server AI Agent v1.0.0",
        "demo_mode": agent.config.demo_mode if agent else False,
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            # Process different message types
            if message["type"] == "command":
                result = await agent.execute_action(
                    action_level=message["action_level"],
                    command=message["command"],
                    parameters=message.get("parameters", {})
                )
                await websocket.send_text(json.dumps({
                    "type": "response",
                    "data": result
                }, ensure_ascii=False))
            elif message["type"] == "troubleshoot":
                recommendations = await agent.troubleshoot_issue(
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
            "message": str(e)
        }, ensure_ascii=False))

# ─── Health Scoring Endpoint ───────────────────────────────────────
@app.post("/health-score")
async def calculate_health_score(request: dict):
    """Calculate comprehensive health score for server"""
    try:
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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Health Monitoring Endpoints ───────────────────────────────────
@app.post("/monitoring/start")
async def start_health_monitoring():
    """Start automated health monitoring"""
    try:
        from core.health_monitor import health_monitor
        
        if not agent.is_connected():
            raise HTTPException(status_code=400, detail="Not connected to server")
        
        # Set server info and client
        server_info = {
            "hostname": agent.current_session.server_host,
            "connected_at": datetime.utcnow().isoformat()
        }
        health_monitor.set_server_info(server_info, agent.redfish_client)
        
        await health_monitor.start_monitoring()
        
        return {
            "status": "success",
            "message": "Health monitoring started"
        }
    except Exception as e:
        logger.error(f"Monitoring start error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/monitoring/stop")
async def stop_health_monitoring():
    """Stop automated health monitoring"""
    try:
        from core.health_monitor import health_monitor
        await health_monitor.stop_monitoring()
        
        return {
            "status": "success",
            "message": "Health monitoring stopped"
        }
    except Exception as e:
        logger.error(f"Monitoring stop error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fleet", response_class=HTMLResponse)
async def get_fleet_dashboard():
    """Serve the fleet management dashboard"""
    return FileResponse('templates/fleet.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/api/fleet/overview")
async def get_fleet_overview():
    """Get fleet overview data"""
    try:
        overview = fleet_manager.get_fleet_overview()
        return {
            "status": "success",
            "data": overview
        }
    except Exception as e:
        logger.error(f"Error getting fleet overview: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/servers")
async def add_fleet_server(server_data: dict):
    """Add a new server to the fleet"""
    try:
        server_id = fleet_manager.add_server(
            name=server_data.get('name'),
            host=server_data.get('host'),
            username=server_data.get('username'),
            password=server_data.get('password'),
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/servers/{server_id}/connect")
async def connect_fleet_server(server_id: str):
    """Connect to a specific server in the fleet"""
    try:
        success = await fleet_manager.connect_server(server_id)
        
        return {
            "status": "success" if success else "error",
            "message": "Connected successfully" if success else "Connection failed"
        }
    except Exception as e:
        logger.error(f"Error connecting to server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/servers/{server_id}/disconnect")
async def disconnect_fleet_server(server_id: str):
    """Disconnect from a specific server in the fleet"""
    try:
        success = await fleet_manager.disconnect_server(server_id)
        
        return {
            "status": "success" if success else "error",
            "message": "Disconnected successfully" if success else "Disconnection failed"
        }
    except Exception as e:
        logger.error(f"Error disconnecting from server {server_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/connect-all")
async def connect_all_fleet_servers():
    """Connect to all servers in the fleet"""
    try:
        results = await fleet_manager.connect_all_servers()
        
        return {
            "status": "success",
            "results": results,
            "message": f"Connected to {sum(results.values())} of {len(results)} servers"
        }
    except Exception as e:
        logger.error(f"Error connecting to all servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/disconnect-all")
async def disconnect_all_fleet_servers():
    """Disconnect from all servers in the fleet"""
    try:
        results = await fleet_manager.disconnect_all_servers()
        
        return {
            "status": "success",
            "results": results,
            "message": f"Disconnected from {sum(results.values())} of {len(results)} servers"
        }
    except Exception as e:
        logger.error(f"Error disconnecting from all servers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fleet/servers/{server_id}")
async def get_fleet_server(server_id: str):
    """Get details for a specific server"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/fleet/servers/{server_id}")
async def update_fleet_server(server_id: str, server_data: dict):
    """Update a server in the fleet"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/fleet/servers/{server_id}")
async def delete_fleet_server(server_id: str):
    """Delete a server from the fleet"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/servers/{server_id}/diagnostics")
async def run_server_diagnostics(server_id: str):
    """Run diagnostics on a specific server"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/health-check")
async def run_fleet_health_check():
    """Run health check on all connected servers"""
    try:
        results = await fleet_manager.run_fleet_health_check()
        
        return {
            "status": "success",
            "data": results,
            "message": f"Health check completed for {results['connected_servers']} servers"
        }
    except Exception as e:
        logger.error(f"Fleet health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fleet/alerts")
async def get_fleet_alerts(hours: int = 24, limit: int = 100):
    """Get recent alerts from all servers"""
    try:
        alerts = fleet_manager.get_recent_alerts(hours, limit)
        
        return {
            "status": "success",
            "alerts": alerts,
            "total": len(alerts)
        }
    except Exception as e:
        logger.error(f"Error getting fleet alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/mobile", response_class=HTMLResponse)
async def get_mobile_dashboard():
    """Serve the mobile-responsive dashboard"""
    return FileResponse('templates/mobile.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/monitoring", response_class=HTMLResponse)
async def get_realtime_dashboard():
    """Serve the real-time monitoring dashboard"""
    return FileResponse('templates/realtime.html', headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.websocket("/ws/monitoring")
async def websocket_monitoring(websocket: WebSocket):
    """WebSocket endpoint for real-time monitoring"""
    await websocket.accept()
    
    # Add connection to monitor
    realtime_monitor.add_websocket_connection(websocket)
    
    try:
        # Start monitoring if not already running
        if not realtime_monitor.monitoring_active and agent.is_connected():
            await realtime_monitor.start_monitoring(agent.redfish_client)
        
        # Send initial metrics
        current_metrics = realtime_monitor.get_current_metrics()
        await websocket.send_text(json.dumps({
            "type": "initial_metrics",
            "data": current_metrics
        }, ensure_ascii=False))
        
        # Keep connection alive and handle messages
        while True:
            try:
                message = await websocket.receive_text()
                data = json.loads(message)
                
                # Handle client messages
                if data.get("action") == "start_monitoring":
                    if agent.is_connected():
                        await realtime_monitor.start_monitoring(agent.redfish_client)
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
                    "data": {"message": str(e)}
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/monitoring/metrics/{metric_name}/history")
async def get_metric_history(metric_name: str, minutes: int = 60):
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Fleet Group Management Endpoints ──────────────────────────────
@app.get("/api/fleet/groups")
async def get_fleet_groups():
    """Get all server groups"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/groups")
async def create_fleet_group(group_data: dict):
    """Create a new server group"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/fleet/groups/{group_name}")
async def delete_fleet_group(group_name: str):
    """Delete a server group"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/groups/{group_name}/servers/{server_id}")
async def add_server_to_group(group_name: str, server_id: str):
    """Add a server to a group"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/fleet/groups/{group_name}/servers/{server_id}")
async def remove_server_from_group(group_name: str, server_id: str):
    """Remove a server from a group"""
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Fleet Analytics Endpoints ──────────────────────────────
@app.get("/api/fleet/analytics")
async def get_fleet_analytics(time_range: str = "24h", metric: str = "health"):
    """Get fleet analytics data"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/fleet/analytics/report")
async def generate_fleet_report(report_config: dict = {}):
    """Generate a fleet analytics report"""
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Export Endpoints ──────────────────────────────
@app.get("/api/fleet/export/servers")
async def export_fleet_servers(format: str = "json"):
    """Export fleet servers data"""
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/fleet/export/alerts")
async def export_fleet_alerts(format: str = "json", hours: int = 24):
    """Export fleet alerts data"""
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Server Snapshot / Quick Status Endpoint ─────────────────────
# Stores snapshots in memory for timeline
_health_snapshots = []

@app.get("/api/server/snapshot")
async def get_server_snapshot():
    """Get a comprehensive snapshot of current server status - used for timeline/history"""
    try:
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
        except: pass
        
        # Collect power
        try:
            power = await agent.execute_action(ActionLevel.READ_ONLY, "get_power_supplies", {})
            snapshot["power"] = power
        except: pass
        
        # Collect health
        try:
            health = await agent.execute_action(ActionLevel.READ_ONLY, "health_check", {})
            snapshot["health"] = health
        except: pass
        
        # Store snapshot
        _health_snapshots.append(snapshot)
        if len(_health_snapshots) > 100:
            _health_snapshots.pop(0)
        
        return {"status": "success", "snapshot": snapshot}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Snapshot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/server/timeline")
async def get_server_timeline(limit: int = 50):
    """Get health snapshot timeline"""
    try:
        return {
            "status": "success",
            "timeline": _health_snapshots[-limit:],
            "total": len(_health_snapshots)
        }
    except Exception as e:
        logger.error(f"Timeline error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ─── Quick Diagnostics Summary ─────────────────────────────────
@app.get("/api/server/diagnostics-summary")
async def get_diagnostics_summary():
    """Get a quick one-shot diagnostics summary of the connected server"""
    try:
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
        except: pass
        
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
        except: pass
        
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
        raise HTTPException(status_code=500, detail=str(e))

# ─── Server Comparison ──────────────────────────────────────────
@app.post("/api/fleet/compare")
async def compare_fleet_servers(request: dict):
    """Compare two or more servers side by side"""
    try:
        server_ids = request.get("server_ids", [])
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
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
