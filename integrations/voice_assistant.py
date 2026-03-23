"""
Voice Assistant Integration for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime
import json
import re

from models.server_models import ActionLevel
from core.agent_core import DellAIAgent

logger = logging.getLogger(__name__)

class VoiceAssistant:
    """Voice assistant integration for server management"""
    
    def __init__(self, agent: DellAIAgent):
        self.agent = agent
        self.command_patterns = self._initialize_command_patterns()
        self.session_context = {}
        self.last_command_time = None
        
    def _initialize_command_patterns(self) -> Dict[str, Dict]:
        """Initialize voice command patterns"""
        return {
            # Server Information Commands
            "server_info": {
                "patterns": [
                    r"what is the server (status|info)",
                    r"tell me about the server",
                    r"server information",
                    r"check server status",
                    r"how is the server doing"
                ],
                "action": "get_server_info",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Here's the current server information: {info}"
            },
            
            # Health Check Commands
            "health_check": {
                "patterns": [
                    r"check (server )?health",
                    r"health check",
                    r"how is the server health",
                    r"server health status",
                    r"is the server healthy"
                ],
                "action": "health_check",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Server health check completed. Overall status: {status}"
            },
            
            # Temperature Commands
            "temperature": {
                "patterns": [
                    r"what (are|is) the (server )?temperatures?",
                    r"check temperature",
                    r"how hot is the server",
                    r"server temperature",
                    r"temperature readings"
                ],
                "action": "get_temperature_sensors",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Current temperature readings: {temperatures}"
            },
            
            # Performance Commands
            "performance": {
                "patterns": [
                    r"check (server )?performance",
                    r"how is the server performing",
                    r"performance analysis",
                    r"server performance",
                    r"performance metrics"
                ],
                "action": "performance_analysis",
                "action_level": ActionLevel.DIAGNOSTIC,
                "response_template": "Performance analysis completed. CPU: {cpu}%, Memory: {memory}%"
            },
            
            # Log Collection Commands
            "collect_logs": {
                "patterns": [
                    r"collect (server )?logs",
                    r"get the logs",
                    r"show me the logs",
                    r"log collection",
                    r"system logs"
                ],
                "action": "collect_logs",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Collected {count} log entries. Recent issues: {issues}"
            },
            
            # Troubleshooting Commands
            "troubleshoot": {
                "patterns": [
                    r"troubleshoot (.+)",
                    r"help me with (.+)",
                    r"diagnose (.+)",
                    r"what's wrong with (.+)",
                    r"investigate (.+)"
                ],
                "action": "troubleshoot_issue",
                "action_level": ActionLevel.DIAGNOSTIC,
                "response_template": "AI troubleshooting for '{issue}' found {count} recommendations"
            },
            
            # Power Commands
            "power_on": {
                "patterns": [
                    r"power on (the )?server",
                    r"turn on (the )?server",
                    r"start (the )?server",
                    r"boot (the )?server"
                ],
                "action": "power_on",
                "action_level": ActionLevel.FULL_CONTROL,
                "response_template": "Server power on initiated. Please wait for startup to complete."
            },
            
            "power_off": {
                "patterns": [
                    r"power off (the )?server",
                    r"turn off (the )?server",
                    r"shutdown (the )?server",
                    r"shut down (the )?server"
                ],
                "action": "power_off",
                "action_level": ActionLevel.FULL_CONTROL,
                "response_template": "Server power off initiated. System will shutdown gracefully."
            },
            
            "restart": {
                "patterns": [
                    r"restart (the )?server",
                    r"reboot (the )?server",
                    r"power cycle (the )?server",
                    r"restart the system"
                ],
                "action": "restart_server",
                "action_level": ActionLevel.FULL_CONTROL,
                "response_template": "Server restart initiated. System will reboot."
            },
            
            # Fan Commands
            "fans": {
                "patterns": [
                    r"check (the )?fans?",
                    r"fan status",
                    r"how are the fans",
                    r"fan speeds"
                ],
                "action": "get_fans",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Fan status: {fans}"
            },
            
            # Memory Commands
            "memory": {
                "patterns": [
                    r"check (the )?memory",
                    r"memory status",
                    r"how much memory",
                    r"ram usage"
                ],
                "action": "get_memory",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Memory information: {memory}"
            },
            
            # Storage Commands
            "storage": {
                "patterns": [
                    r"check (the )?storage",
                    r"disk status",
                    r"storage information",
                    r"hard drive status"
                ],
                "action": "get_storage_devices",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Storage information: {storage}"
            },
            
            # Network Commands
            "network": {
                "patterns": [
                    r"check (the )?network",
                    r"network status",
                    r"network information",
                    r"connectivity status"
                ],
                "action": "get_network_interfaces",
                "action_level": ActionLevel.READ_ONLY,
                "response_template": "Network information: {network}"
            }
        }
    
    async def process_voice_command(self, command: str, action_level: ActionLevel = ActionLevel.READ_ONLY) -> Dict[str, Any]:
        """Process a voice command and return response"""
        try:
            command = command.lower().strip()
            self.last_command_time = datetime.now()
            
            # Find matching command pattern
            matched_command = self._match_command(command)
            
            if not matched_command:
                return {
                    "status": "error",
                    "message": "I didn't understand that command. Please try again.",
                    "suggestions": self._get_command_suggestions()
                }
            
            # Check action level permissions
            if not self._check_action_level_permission(matched_command["action_level"], action_level):
                return {
                    "status": "error",
                    "message": f"This command requires {matched_command['action_level']} access level.",
                    "current_level": action_level
                }
            
            # Execute the command
            result = await self._execute_voice_command(matched_command, command)
            
            return result
            
        except Exception as e:
            logger.error(f"Voice command processing error: {str(e)}")
            return {
                "status": "error",
                "message": "Sorry, I encountered an error processing your command."
            }
    
    def _match_command(self, command: str) -> Optional[Dict[str, Any]]:
        """Match command against patterns"""
        for command_name, command_info in self.command_patterns.items():
            for pattern in command_info["patterns"]:
                match = re.search(pattern, command, re.IGNORECASE)
                if match:
                    return {
                        "name": command_name,
                        "action": command_info["action"],
                        "action_level": command_info["action_level"],
                        "response_template": command_info["response_template"],
                        "match": match
                    }
        return None
    
    def _check_action_level_permission(self, required_level: ActionLevel, current_level: ActionLevel) -> bool:
        """Check if the current action level permits the required action"""
        level_hierarchy = {
            ActionLevel.READ_ONLY: 1,
            ActionLevel.DIAGNOSTIC: 2,
            ActionLevel.FULL_CONTROL: 3
        }
        
        return level_hierarchy[current_level] >= level_hierarchy[required_level]
    
    async def _execute_voice_command(self, matched_command: Dict[str, Any], original_command: str) -> Dict[str, Any]:
        """Execute the matched voice command"""
        command_name = matched_command["name"]
        action = matched_command["action"]
        match = matched_command["match"]
        
        try:
            # Handle special cases for troubleshooting
            if command_name == "troubleshoot":
                issue_description = match.group(1) if match.groups() else original_command
                result = await self.agent.troubleshoot_issue(issue_description, ActionLevel.DIAGNOSTIC)
                
                return {
                    "status": "success",
                    "command": command_name,
                    "message": matched_command["response_template"].format(
                        issue=issue_description,
                        count=len(result)
                    ),
                    "data": {
                        "recommendations": [rec.model_dump() for rec in result],
                        "issue": issue_description
                    }
                }
            
            # Handle standard commands
            else:
                parameters = {}
                
                # Add any extracted parameters from the command
                if match.groups():
                    parameters["extracted"] = match.groups()
                
                # Execute the action
                result = await self.agent.execute_action(
                    action_level=matched_command["action_level"],
                    command=action,
                    parameters=parameters
                )
                
                # Format response based on command type
                response_message = self._format_response(command_name, result, matched_command["response_template"])
                
                return {
                    "status": "success",
                    "command": command_name,
                    "message": response_message,
                    "data": result
                }
                
        except Exception as e:
            logger.error(f"Command execution error: {str(e)}")
            return {
                "status": "error",
                "command": command_name,
                "message": f"Failed to execute {command_name}: {str(e)}"
            }
    
    def _format_response(self, command_name: str, result: Dict[str, Any], template: str) -> str:
        """Format response based on command type and results"""
        
        if command_name == "server_info":
            info = result.get("server_info", {})
            if info:
                return f"Server {info.get('model', 'Unknown')} with service tag {info.get('service_tag', 'Unknown')}. Status: {info.get('status', 'Unknown')}"
        
        elif command_name == "health_check":
            health = result.get("health_status", {})
            if health:
                overall_status = health.get("overall_status", "Unknown")
                critical_issues = len(health.get("critical_issues", []))
                warnings = len(health.get("warnings", []))
                return f"Overall health status: {overall_status}. {critical_issues} critical issues, {warnings} warnings."
        
        elif command_name == "temperature":
            temps = result.get("temperatures", [])
            if temps:
                temp_readings = [f"{t.get('name', 'Unknown')}: {t.get('reading_celsius', 'N/A')}°C" for t in temps[:3]]
                return f"Temperature readings: {', '.join(temp_readings)}"
        
        elif command_name == "performance":
            perf = result.get("performance_metrics", {})
            cpu = perf.get("cpu_utilization", 0)
            memory = perf.get("memory_utilization", 0)
            return f"Performance: CPU {cpu:.1f}%, Memory {memory:.1f}%"
        
        elif command_name == "collect_logs":
            logs = result.get("logs", [])
            recent_errors = [log for log in logs[:5] if log.get("severity") in ["error", "critical"]]
            return f"Collected {len(logs)} log entries. {len(recent_errors)} recent issues found."
        
        elif command_name == "fans":
            fans = result.get("fans", [])
            if fans:
                fan_info = [f"{f.get('name', 'Unknown')}: {f.get('speed_rpm', 'N/A')} RPM" for f in fans[:3]]
                return f"Fan status: {', '.join(fan_info)}"
        
        elif command_name == "memory":
            memory = result.get("memory", [])
            if memory:
                total_memory = sum(m.get("size_gb", 0) for m in memory)
                return f"Total memory: {total_memory} GB across {len(memory)} modules"
        
        elif command_name == "storage":
            storage = result.get("storage_devices", [])
            if storage:
                storage_info = [f"{s.get('name', 'Unknown')}: {s.get('capacity_gb', 0)} GB" for s in storage[:3]]
                return f"Storage devices: {', '.join(storage_info)}"
        
        elif command_name == "network":
            network = result.get("network_interfaces", [])
            if network:
                network_info = [f"{n.get('name', 'Unknown')}: {n.get('status', 'Unknown')}" for n in network[:3]]
                return f"Network interfaces: {', '.join(network_info)}"
        
        # Default response
        return f"Command {command_name} completed successfully."
    
    def _get_command_suggestions(self) -> List[str]:
        """Get suggestions for available commands"""
        suggestions = [
            "Check server health",
            "Check server temperature",
            "Check server performance",
            "Collect system logs",
            "Troubleshoot server issues",
            "Check fan status",
            "Check memory status",
            "Check storage status",
            "Check network status"
        ]
        
        return suggestions
    
    def get_available_commands(self, action_level: ActionLevel = ActionLevel.READ_ONLY) -> List[Dict[str, Any]]:
        """Get list of available commands for the current action level"""
        available_commands = []
        
        for command_name, command_info in self.command_patterns.items():
            if self._check_action_level_permission(command_info["action_level"], action_level):
                available_commands.append({
                    "name": command_name,
                    "action": command_info["action"],
                    "action_level": command_info["action_level"],
                    "patterns": command_info["patterns"]
                })
        
        return available_commands
    
    async def start_voice_session(self, session_id: str, action_level: ActionLevel = ActionLevel.READ_ONLY):
        """Start a voice session"""
        self.session_context[session_id] = {
            "started_at": datetime.now(),
            "action_level": action_level,
            "command_count": 0,
            "last_command": None
        }
        
        logger.info(f"Started voice session: {session_id}")
    
    async def end_voice_session(self, session_id: str):
        """End a voice session"""
        if session_id in self.session_context:
            session_info = self.session_context[session_id]
            duration = datetime.now() - session_info["started_at"]
            
            logger.info(f"Ended voice session: {session_id}, duration: {duration}, commands: {session_info['command_count']}")
            del self.session_context[session_id]
    
    def get_session_info(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a voice session"""
        return self.session_context.get(session_id)
    
    def get_help_text(self, action_level: ActionLevel = ActionLevel.READ_ONLY) -> str:
        """Get help text for available commands"""
        available_commands = self.get_available_commands(action_level)
        
        help_text = "Available voice commands:\n\n"
        
        for command in available_commands:
            command_name = command["name"].replace("_", " ").title()
            patterns = command["patterns"][:2]  # Show first 2 patterns
            
            help_text += f"• {command_name}:\n"
            for pattern in patterns:
                help_text += f"  - \"{pattern}\"\n"
            help_text += "\n"
        
        help_text += "\nYou can also ask me to troubleshoot issues by saying \"troubleshoot [issue description]\""
        
        return help_text
    
    async def process_continuous_voice(self, audio_stream: Callable, session_id: str, 
                                    action_level: ActionLevel = ActionLevel.READ_ONLY):
        """Process continuous voice input (for advanced integration)"""
        # This would integrate with speech-to-text services
        # For now, it's a placeholder for future enhancement
        
        if session_id not in self.session_context:
            await self.start_voice_session(session_id, action_level)
        
        # In a real implementation, this would:
        # 1. Convert audio to text using STT
        # 2. Process the text command
        # 3. Convert response to speech using TTS
        # 4. Stream audio back
        
        logger.info("Continuous voice processing not yet implemented")
        
        return {
            "status": "not_implemented",
            "message": "Continuous voice processing requires STT/TTS integration"
        }
