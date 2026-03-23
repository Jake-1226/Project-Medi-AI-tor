"""
Virtual Assistant API for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
from fastapi import HTTPException
from pydantic import BaseModel

from core.agent_core import DellAIAgent
from integrations.voice_assistant import VoiceAssistant
from models.server_models import ActionLevel

logger = logging.getLogger(__name__)

class VirtualAssistantRequest(BaseModel):
    """Virtual assistant request model"""
    command: str
    action_level: ActionLevel = ActionLevel.READ_ONLY
    session_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None

class VirtualAssistantResponse(BaseModel):
    """Virtual assistant response model"""
    status: str
    command: str
    message: str
    data: Optional[Dict[str, Any]] = None
    suggestions: Optional[List[str]] = None
    session_id: Optional[str] = None
    processing_time: Optional[float] = None

class VirtualAssistantAPI:
    """Virtual Assistant API for external integrations"""
    
    def __init__(self, agent: DellAIAgent):
        self.agent = agent
        self.voice_assistant = VoiceAssistant(agent)
        self.active_sessions: Dict[str, Dict] = {}
        self.command_history: List[Dict] = []
        
    async def process_command(self, request: VirtualAssistantRequest) -> VirtualAssistantResponse:
        """Process virtual assistant command"""
        start_time = datetime.now()
        
        try:
            # Create or get session
            session_id = request.session_id or self._create_session()
            session = self._get_or_create_session(session_id)
            
            # Process the command
            result = await self.voice_assistant.process_voice_command(
                request.command, 
                request.action_level
            )
            
            # Update session
            session["last_activity"] = datetime.now()
            session["command_count"] += 1
            session["last_command"] = request.command
            
            # Add to history
            history_entry = {
                "session_id": session_id,
                "command": request.command,
                "action_level": request.action_level,
                "timestamp": datetime.now().isoformat(),
                "status": result.get("status", "unknown"),
                "response": result.get("message", "")
            }
            self.command_history.append(history_entry)
            
            # Keep only last 1000 entries
            if len(self.command_history) > 1000:
                self.command_history = self.command_history[-1000:]
            
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return VirtualAssistantResponse(
                status=result.get("status", "unknown"),
                command=result.get("command", request.command),
                message=result.get("message", ""),
                data=result.get("data"),
                suggestions=result.get("suggestions"),
                session_id=session_id,
                processing_time=processing_time
            )
            
        except Exception as e:
            logger.error(f"Virtual assistant command processing error: {str(e)}")
            processing_time = (datetime.now() - start_time).total_seconds()
            
            return VirtualAssistantResponse(
                status="error",
                command=request.command,
                message=f"Error processing command: {str(e)}",
                session_id=request.session_id,
                processing_time=processing_time
            )
    
    def _create_session(self) -> str:
        """Create a new session"""
        import uuid
        session_id = str(uuid.uuid4())
        
        self.active_sessions[session_id] = {
            "created_at": datetime.now(),
            "last_activity": datetime.now(),
            "command_count": 0,
            "last_command": None,
            "context": {}
        }
        
        return session_id
    
    def _get_or_create_session(self, session_id: str) -> Dict:
        """Get existing session or create new one"""
        if session_id not in self.active_sessions:
            self.active_sessions[session_id] = {
                "created_at": datetime.now(),
                "last_activity": datetime.now(),
                "command_count": 0,
                "last_command": None,
                "context": {}
            }
        
        return self.active_sessions[session_id]
    
    async def start_session(self, action_level: ActionLevel = ActionLevel.READ_ONLY) -> Dict[str, Any]:
        """Start a new virtual assistant session"""
        session_id = self._create_session()
        session = self.active_sessions[session_id]
        session["action_level"] = action_level
        
        await self.voice_assistant.start_voice_session(session_id, action_level)
        
        return {
            "session_id": session_id,
            "action_level": action_level,
            "created_at": session["created_at"].isoformat(),
            "available_commands": self.voice_assistant.get_available_commands(action_level)
        }
    
    async def end_session(self, session_id: str) -> Dict[str, Any]:
        """End a virtual assistant session"""
        if session_id not in self.active_sessions:
            raise HTTPException(status_code=404, detail="Session not found")
        
        session = self.active_sessions[session_id]
        await self.voice_assistant.end_voice_session(session_id)
        
        session_info = session.copy()
        del self.active_sessions[session_id]
        
        return {
            "session_id": session_id,
            "ended_at": datetime.now().isoformat(),
            "session_duration": (datetime.now() - session["created_at"]).total_seconds(),
            "command_count": session["command_count"]
        }
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session information"""
        if session_id not in self.active_sessions:
            return None
        
        session = self.active_sessions[session_id]
        return {
            "session_id": session_id,
            "created_at": session["created_at"].isoformat(),
            "last_activity": session["last_activity"].isoformat(),
            "command_count": session["command_count"],
            "last_command": session["last_command"],
            "action_level": session.get("action_level", ActionLevel.READ_ONLY)
        }
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get all active sessions"""
        return [
            {
                "session_id": session_id,
                "created_at": session["created_at"].isoformat(),
                "last_activity": session["last_activity"].isoformat(),
                "command_count": session["command_count"],
                "action_level": session.get("action_level", ActionLevel.READ_ONLY)
            }
            for session_id, session in self.active_sessions.items()
        ]
    
    def get_command_history(self, limit: int = 50, session_id: Optional[str] = None) -> List[Dict]:
        """Get command history"""
        history = self.command_history
        
        if session_id:
            history = [entry for entry in history if entry["session_id"] == session_id]
        
        # Sort by timestamp (most recent first)
        history.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return history[:limit]
    
    async def process_batch_commands(self, commands: List[VirtualAssistantRequest]) -> List[VirtualAssistantResponse]:
        """Process multiple commands in batch"""
        responses = []
        
        for request in commands:
            response = await self.process_command(request)
            responses.append(response)
        
        return responses
    
    def get_available_commands(self, action_level: ActionLevel = ActionLevel.READ_ONLY) -> List[Dict[str, Any]]:
        """Get available commands for action level"""
        commands = self.voice_assistant.get_available_commands(action_level)
        
        return [
            {
                "name": cmd["name"],
                "action": cmd["action"],
                "action_level": cmd["action_level"],
                "patterns": cmd["patterns"]
            }
            for cmd in commands
        ]
    
    def get_help_text(self, action_level: ActionLevel = ActionLevel.READ_ONLY) -> str:
        """Get help text for available commands"""
        return self.voice_assistant.get_help_text(action_level)
    
    async def get_contextual_suggestions(self, partial_command: str, 
                                       action_level: ActionLevel = ActionLevel.READ_ONLY) -> List[str]:
        """Get contextual suggestions based on partial command"""
        available_commands = self.voice_assistant.get_available_commands(action_level)
        suggestions = []
        
        partial_lower = partial_command.lower()
        
        for cmd in available_commands:
            for pattern in cmd["patterns"]:
                if partial_lower in pattern.lower():
                    suggestions.append(pattern)
                    break
        
        # Add general suggestions if no matches
        if not suggestions:
            suggestions = [
                "Check server health",
                "What is the server temperature?",
                "Get system information",
                "Collect system logs",
                "Check memory usage",
                "Verify network status"
            ]
        
        return suggestions[:10]  # Return top 10 suggestions
    
    def get_session_statistics(self) -> Dict[str, Any]:
        """Get session and command statistics"""
        total_sessions = len(self.active_sessions)
        total_commands = len(self.command_history)
        
        # Calculate average commands per session
        if self.active_sessions:
            avg_commands_per_session = sum(
                session["command_count"] for session in self.active_sessions.values()
            ) / total_sessions
        else:
            avg_commands_per_session = 0
        
        # Get most common commands
        command_counts = {}
        for entry in self.command_history:
            command = entry["command"]
            command_counts[command] = command_counts.get(command, 0) + 1
        
        most_common_commands = sorted(
            command_counts.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:10]
        
        return {
            "active_sessions": total_sessions,
            "total_commands_processed": total_commands,
            "average_commands_per_session": round(avg_commands_per_session, 2),
            "most_common_commands": most_common_commands,
            "session_duration_avg": self._calculate_average_session_duration(),
            "command_success_rate": self._calculate_success_rate()
        }
    
    def _calculate_average_session_duration(self) -> float:
        """Calculate average session duration"""
        if not self.active_sessions:
            return 0.0
        
        total_duration = sum(
            (datetime.now() - session["created_at"]).total_seconds()
            for session in self.active_sessions.values()
        )
        
        return total_duration / len(self.active_sessions)
    
    def _calculate_success_rate(self) -> float:
        """Calculate command success rate"""
        if not self.command_history:
            return 0.0
        
        successful_commands = len([
            entry for entry in self.command_history
            if entry["status"] == "success"
        ])
        
        return (successful_commands / len(self.command_history)) * 100
    
    async def cleanup_expired_sessions(self, max_age_hours: int = 24) -> int:
        """Clean up expired sessions"""
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)
        
        expired_sessions = [
            session_id for session_id, session in self.active_sessions.items()
            if session["last_activity"] < cutoff_time
        ]
        
        for session_id in expired_sessions:
            await self.end_session(session_id)
        
        return len(expired_sessions)
    
    def export_session_data(self, format: str = "json") -> Dict[str, Any]:
        """Export session data for analysis"""
        if format == "json":
            return {
                "active_sessions": self.get_active_sessions(),
                "command_history": self.get_command_history(limit=1000),
                "statistics": self.get_session_statistics(),
                "export_timestamp": datetime.now().isoformat()
            }
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def get_integration_endpoints(self) -> Dict[str, str]:
        """Get available integration endpoints for virtual assistants"""
        return {
            "process_command": "/api/virtual-assistant/command",
            "start_session": "/api/virtual-assistant/session/start",
            "end_session": "/api/virtual-assistant/session/{session_id}/end",
            "get_session_info": "/api/virtual-assistant/session/{session_id}",
            "get_commands": "/api/virtual-assistant/commands",
            "get_help": "/api/virtual-assistant/help",
            "get_suggestions": "/api/virtual-assistant/suggestions",
            "batch_commands": "/api/virtual-assistant/batch",
            "statistics": "/api/virtual-assistant/statistics"
        }
    
    async def validate_command(self, command: str, action_level: ActionLevel) -> Dict[str, Any]:
        """Validate if command can be executed"""
        available_commands = self.voice_assistant.get_available_commands(action_level)
        
        matched_command = self.voice_assistant._match_command(command.lower())
        
        if not matched_command:
            return {
                "valid": False,
                "reason": "Command not recognized",
                "suggestions": self.get_available_commands(action_level)[:5]
            }
        
        # Check action level permission
        if not self.voice_assistant._check_action_level_permission(
            matched_command["action_level"], action_level
        ):
            return {
                "valid": False,
                "reason": f"Command requires {matched_command['action_level']} access level",
                "required_level": matched_command["action_level"],
                "current_level": action_level
            }
        
        return {
            "valid": True,
            "matched_command": matched_command,
            "estimated_execution_time": self._estimate_command_execution_time(matched_command)
        }
    
    def _estimate_command_execution_time(self, matched_command: Dict[str, Any]) -> str:
        """Estimate command execution time"""
        time_estimates = {
            "get_server_info": "5-10 seconds",
            "health_check": "10-15 seconds",
            "collect_logs": "15-30 seconds",
            "get_temperature_sensors": "5-10 seconds",
            "get_fans": "5-10 seconds",
            "performance_analysis": "20-30 seconds",
            "troubleshoot_issue": "30-60 seconds",
            "power_on": "30-60 seconds",
            "power_off": "10-20 seconds",
            "restart_server": "60-120 seconds"
        }
        
        return time_estimates.get(
            matched_command["action"], 
            "10-30 seconds"  # Default estimate
        )
