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
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import json
import uvicorn

from core.agent_core import DellAIAgent
from core.config import AgentConfig
from core.automation_engine import AutomationEngine
from core.multi_server_manager import MultiServerManager
from core.analytics_engine import AnalyticsEngine
from ai.predictive_analytics import PredictiveAnalytics
from ai.predictive_maintenance import PredictiveMaintenance
from ai.troubleshooting_engine import TroubleshootingEngine
from ai.log_analyzer import LogAnalyzer
from integrations.voice_assistant import VoiceAssistant
from api.third_party_api import ThirdPartyAPI

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

# Global agent instance and components
agent = None
automation_engine = None
multi_server_manager = None
analytics_engine = None
predictive_analytics = None
predictive_maintenance = None
voice_assistant = None
third_party_api = None

# Pydantic models for API
class ServerConnection(BaseModel):
    host: str
    username: str
    password: str
    port: Optional[int] = 443

class AgentActionRequest(BaseModel):
    action_level: ActionLevel
    command: Optional[str] = None
    parameters: Optional[Dict[str, Any]] = {}

class TroubleshootingTask(BaseModel):
    server_info: ServerConnection
    issue_description: str
    action_level: ActionLevel = ActionLevel.READ_ONLY

@app.on_event("startup")
async def startup_event():
    """Initialize the AI agent and all components on startup"""
    global agent, automation_engine, multi_server_manager, analytics_engine
    global predictive_analytics, predictive_maintenance, voice_assistant, third_party_api
    
    config = AgentConfig()
    
    # Initialize core components
    agent = DellAIAgent(config)
    predictive_analytics = PredictiveAnalytics(config)
    predictive_maintenance = PredictiveMaintenance(predictive_analytics)
    analytics_engine = AnalyticsEngine()
    automation_engine = AutomationEngine(agent)
    multi_server_manager = MultiServerManager(config)
    voice_assistant = VoiceAssistant(agent)
    third_party_api = ThirdPartyAPI(agent)
    
    logger.info("Dell AI Agent and all components initialized successfully")

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def get_dashboard():
    """Serve the main dashboard"""
    return FileResponse('templates/dashboard.html')

@app.post("/connect")
async def connect_to_server(connection: ServerConnection):
    """Connect to a Dell server using Redfish API"""
    try:
        success = await agent.connect_to_server(
            host=connection.host,
            username=connection.username,
            password=connection.password,
            port=connection.port
        )
        
        if success:
            return {"status": "success", "message": "Connected to server successfully"}
        else:
            raise HTTPException(status_code=400, detail="Failed to connect to server")
            
    except Exception as e:
        logger.error(f"Connection error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/execute")
async def execute_action(request: AgentActionRequest):
    """Execute an agent action based on the specified action level"""
    try:
        result = await agent.execute_action(
            action_level=request.action_level,
            command=request.command,
            parameters=request.parameters
        )
        return {"status": "success", "data": result}
        
    except Exception as e:
        logger.error(f"Action execution error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/troubleshoot")
async def troubleshoot_server(request: TroubleshootingTask):
    """Start AI-powered troubleshooting for a server issue"""
    try:
        # First connect to the server
        await agent.connect_to_server(
            host=request.server_info.host,
            username=request.server_info.username,
            password=request.server_info.password,
            port=request.server_info.port
        )
        
        # Start troubleshooting
        recommendations = await agent.troubleshoot_issue(
            issue_description=request.issue_description,
            action_level=request.action_level
        )
        
        return {
            "status": "success", 
            "recommendations": recommendations,
            "issue": request.issue_description
        }
        
    except Exception as e:
        logger.error(f"Troubleshooting error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """API health check endpoint"""
    return {"status": "healthy", "agent": "Dell Server AI Agent v1.0.0"}

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
                }))
            elif message["type"] == "troubleshoot":
                recommendations = await agent.troubleshoot_issue(
                    issue_description=message["issue_description"],
                    action_level=message["action_level"]
                )
                await websocket.send_text(json.dumps({
                    "type": "troubleshooting_result",
                    "recommendations": recommendations
                }))
                
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
        await websocket.send_text(json.dumps({
            "type": "error",
            "message": str(e)
        }))

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
