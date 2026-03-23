"""
Comprehensive Logging and Audit Trails for Dell Server AI Agent
"""

import logging
import json
import os
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import threading
from pathlib import Path
import hashlib

class AuditEventType(str, Enum):
    USER_LOGIN = "user_login"
    USER_LOGOUT = "user_logout"
    SERVER_CONNECT = "server_connect"
    SERVER_DISCONNECT = "server_disconnect"
    COMMAND_EXECUTE = "command_execute"
    CONFIG_CHANGE = "config_change"
    ERROR_OCCURRED = "error_occurred"
    SECURITY_VIOLATION = "security_violation"
    DATA_ACCESS = "data_access"
    SYSTEM_STARTUP = "system_startup"
    SYSTEM_SHUTDOWN = "system_shutdown"
    WORKFLOW_EXECUTE = "workflow_execute"
    API_REQUEST = "api_request"
    INTEGRATION_EVENT = "integration_event"

class AuditSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class AuditEvent:
    """Audit event data structure"""
    timestamp: datetime
    event_type: AuditEventType
    severity: AuditSeverity
    user_id: Optional[str]
    session_id: Optional[str]
    server_id: Optional[str]
    action: str
    details: Dict[str, Any]
    source_ip: Optional[str]
    user_agent: Optional[str]
    success: bool
    error_message: Optional[str] = None
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data
    
    def get_hash(self) -> str:
        """Generate hash for event deduplication"""
        hash_data = f"{self.event_type}:{self.user_id}:{self.action}:{self.timestamp}"
        return hashlib.sha256(hash_data.encode()).hexdigest()[:16]

class AuditLogger:
    """Comprehensive audit logging system"""
    
    def __init__(self, log_dir: str = "logs", max_file_size_mb: int = 100, 
                 max_files: int = 10, enable_file_rotation: bool = True):
        self.log_dir = Path(log_dir)
        self.max_file_size = max_file_size_mb * 1024 * 1024
        self.max_files = max_files
        self.enable_file_rotation = enable_file_rotation
        
        # Create log directory
        self.log_dir.mkdir(exist_ok=True)
        
        # Audit event storage
        self.events: List[AuditEvent] = []
        self.event_hashes: set = set()
        self.max_events = 10000  # Keep last 10k events in memory
        
        # Thread safety
        self._lock = threading.RLock()
        
        # Setup file logger
        self._setup_file_logger()
        
        # Setup console logger
        self._setup_console_logger()
        
        # Statistics
        self.stats = {
            "total_events": 0,
            "events_by_type": {},
            "events_by_severity": {},
            "events_by_user": {},
            "error_count": 0,
            "last_event_time": None
        }
    
    def _setup_file_logger(self):
        """Setup file-based audit logger"""
        audit_file = self.log_dir / "audit.log"
        
        # Create file handler
        file_handler = logging.FileHandler(audit_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)
        
        # Create audit logger
        self.file_logger = logging.getLogger('audit')
        self.file_logger.setLevel(logging.INFO)
        self.file_logger.addHandler(file_handler)
        self.file_logger.propagate = False
    
    def _setup_console_logger(self):
        """Setup console audit logger"""
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        formatter = logging.Formatter(
            '%(asctime)s - AUDIT - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(formatter)
        
        self.console_logger = logging.getLogger('audit_console')
        self.console_logger.setLevel(logging.INFO)
        self.console_logger.addHandler(console_handler)
        self.console_logger.propagate = False
    
    def log_event(self, event: AuditEvent):
        """Log an audit event"""
        with self._lock:
            # Check for duplicates
            event_hash = event.get_hash()
            if event_hash in self.event_hashes:
                return
            
            # Add to storage
            self.events.append(event)
            self.event_hashes.add(event_hash)
            
            # Maintain memory limit
            if len(self.events) > self.max_events:
                # Remove oldest events
                old_events = self.events[:len(self.events) - self.max_events]
                self.events = self.events[-self.max_events:]
                
                # Update hash set
                self.event_hashes = set(e.get_hash() for e in self.events)
            
            # Update statistics
            self._update_stats(event)
            
            # Log to file
            self._log_to_file(event)
            
            # Log to console based on severity
            self._log_to_console(event)
            
            # Check file rotation
            if self.enable_file_rotation:
                self._check_file_rotation()
    
    def _update_stats(self, event: AuditEvent):
        """Update audit statistics"""
        self.stats["total_events"] += 1
        
        # Event type stats
        event_type = event.event_type.value
        self.stats["events_by_type"][event_type] = self.stats["events_by_type"].get(event_type, 0) + 1
        
        # Severity stats
        severity = event.severity.value
        self.stats["events_by_severity"][severity] = self.stats["events_by_severity"].get(severity, 0) + 1
        
        # User stats
        if event.user_id:
            self.stats["events_by_user"][event.user_id] = self.stats["events_by_user"].get(event.user_id, 0) + 1
        
        # Error count
        if not event.success:
            self.stats["error_count"] += 1
        
        # Last event time
        self.stats["last_event_time"] = event.timestamp
    
    def _log_to_file(self, event: AuditEvent):
        """Log event to file"""
        log_entry = {
            "timestamp": event.timestamp.isoformat(),
            "event_type": event.event_type.value,
            "severity": event.severity.value,
            "user_id": event.user_id,
            "session_id": event.session_id,
            "server_id": event.server_id,
            "action": event.action,
            "details": event.details,
            "source_ip": event.source_ip,
            "user_agent": event.user_agent,
            "success": event.success,
            "error_message": event.error_message,
            "duration_ms": event.duration_ms
        }
        
        self.file_logger.info(json.dumps(log_entry, default=str))
    
    def _log_to_console(self, event: AuditEvent):
        """Log event to console"""
        message_parts = [
            f"[{event.event_type.value.upper()}]",
            f"User: {event.user_id or 'SYSTEM'}",
            f"Action: {event.action}",
            f"Success: {event.success}"
        ]
        
        if event.server_id:
            message_parts.append(f"Server: {event.server_id}")
        
        if not event.success and event.error_message:
            message_parts.append(f"Error: {event.error_message}")
        
        message = " | ".join(message_parts)
        
        if event.severity == AuditSeverity.CRITICAL:
            self.console_logger.critical(message)
        elif event.severity == AuditSeverity.ERROR:
            self.console_logger.error(message)
        elif event.severity == AuditSeverity.WARNING:
            self.console_logger.warning(message)
        else:
            self.console_logger.info(message)
    
    def _check_file_rotation(self):
        """Check if log file needs rotation"""
        audit_file = self.log_dir / "audit.log"
        
        try:
            if audit_file.exists() and audit_file.stat().st_size > self.max_file_size:
                # Rotate file
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = self.log_dir / f"audit_{timestamp}.log"
                
                # Move current file to backup
                audit_file.rename(backup_file)
                
                # Clean up old files
                self._cleanup_old_files()
                
                # Recreate file handler
                self._setup_file_logger()
                
                self.console_logger.info(f"Audit log rotated: {backup_file}")
        except Exception as e:
            self.console_logger.error(f"Failed to rotate audit log: {str(e)}")
    
    def _cleanup_old_files(self):
        """Clean up old audit log files"""
        try:
            audit_files = list(self.log_dir.glob("audit_*.log"))
            audit_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess files
            for old_file in audit_files[self.max_files:]:
                old_file.unlink()
                self.console_logger.info(f"Removed old audit file: {old_file}")
        except Exception as e:
            self.console_logger.error(f"Failed to cleanup old audit files: {str(e)}")
    
    def create_event(self, event_type: AuditEventType, action: str, 
                    user_id: Optional[str] = None, session_id: Optional[str] = None,
                    server_id: Optional[str] = None, details: Optional[Dict[str, Any]] = None,
                    severity: AuditSeverity = AuditSeverity.INFO, source_ip: Optional[str] = None,
                    user_agent: Optional[str] = None, success: bool = True, 
                    error_message: Optional[str] = None, duration_ms: Optional[float] = None) -> AuditEvent:
        """Create and log an audit event"""
        event = AuditEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            severity=severity,
            user_id=user_id,
            session_id=session_id,
            server_id=server_id,
            action=action,
            details=details or {},
            source_ip=source_ip,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            duration_ms=duration_ms
        )
        
        self.log_event(event)
        return event
    
    def log_user_login(self, user_id: str, session_id: str, source_ip: str, 
                      user_agent: str, success: bool = True, error_message: Optional[str] = None):
        """Log user login event"""
        self.create_event(
            event_type=AuditEventType.USER_LOGIN,
            action="User login",
            user_id=user_id,
            session_id=session_id,
            source_ip=source_ip,
            user_agent=user_agent,
            success=success,
            error_message=error_message,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            details={"login_method": "web"}
        )
    
    def log_user_logout(self, user_id: str, session_id: str, duration_minutes: Optional[float] = None):
        """Log user logout event"""
        details = {}
        if duration_minutes:
            details["session_duration_minutes"] = duration_minutes
        
        self.create_event(
            event_type=AuditEventType.USER_LOGOUT,
            action="User logout",
            user_id=user_id,
            session_id=session_id,
            success=True,
            severity=AuditSeverity.INFO,
            details=details
        )
    
    def log_server_connection(self, server_id: str, user_id: str, action: str,
                           success: bool = True, error_message: Optional[str] = None,
                           details: Optional[Dict[str, Any]] = None):
        """Log server connection event"""
        event_type = AuditEventType.SERVER_CONNECT if action == "connect" else AuditEventType.SERVER_DISCONNECT
        
        self.create_event(
            event_type=event_type,
            action=f"Server {action}",
            user_id=user_id,
            server_id=server_id,
            success=success,
            error_message=error_message,
            severity=AuditSeverity.INFO if success else AuditSeverity.ERROR,
            details=details or {}
        )
    
    def log_command_execution(self, command: str, user_id: str, server_id: Optional[str] = None,
                            action_level: str = "read_only", success: bool = True,
                            duration_ms: Optional[float] = None, error_message: Optional[str] = None,
                            details: Optional[Dict[str, Any]] = None):
        """Log command execution event"""
        command_details = details or {}
        command_details["action_level"] = action_level
        
        self.create_event(
            event_type=AuditEventType.COMMAND_EXECUTE,
            action=f"Execute command: {command}",
            user_id=user_id,
            server_id=server_id,
            success=success,
            duration_ms=duration_ms,
            error_message=error_message,
            severity=AuditSeverity.INFO if success else AuditSeverity.WARNING,
            details=command_details
        )
    
    def log_api_request(self, endpoint: str, method: str, user_id: Optional[str] = None,
                        source_ip: Optional[str] = None, user_agent: Optional[str] = None,
                        status_code: Optional[int] = None, duration_ms: Optional[float] = None,
                        success: bool = True, error_message: Optional[str] = None,
                        request_details: Optional[Dict[str, Any]] = None):
        """Log API request event"""
        details = request_details or {}
        details["method"] = method
        details["endpoint"] = endpoint
        details["status_code"] = status_code
        
        severity = AuditSeverity.INFO
        if not success or (status_code and status_code >= 400):
            severity = AuditSeverity.WARNING if status_code < 500 else AuditSeverity.ERROR
        
        self.create_event(
            event_type=AuditEventType.API_REQUEST,
            action=f"API {method} {endpoint}",
            user_id=user_id,
            source_ip=source_ip,
            user_agent=user_agent,
            success=success,
            duration_ms=duration_ms,
            error_message=error_message,
            severity=severity,
            details=details
        )
    
    def log_security_event(self, event_type: AuditEventType, action: str, 
                          user_id: Optional[str] = None, source_ip: Optional[str] = None,
                          details: Optional[Dict[str, Any]] = None):
        """Log security-related event"""
        self.create_event(
            event_type=event_type,
            action=action,
            user_id=user_id,
            source_ip=source_ip,
            success=False,  # Security events are typically failures
            severity=AuditSeverity.CRITICAL,
            details=details or {}
        )
    
    def get_events(self, limit: int = 100, event_type: Optional[AuditEventType] = None,
                   user_id: Optional[str] = None, server_id: Optional[str] = None,
                   start_time: Optional[datetime] = None, end_time: Optional[datetime] = None) -> List[Dict[str, Any]]:
        """Get filtered audit events"""
        with self._lock:
            filtered_events = self.events.copy()
        
        # Apply filters
        if event_type:
            filtered_events = [e for e in filtered_events if e.event_type == event_type]
        
        if user_id:
            filtered_events = [e for e in filtered_events if e.user_id == user_id]
        
        if server_id:
            filtered_events = [e for e in filtered_events if e.server_id == server_id]
        
        if start_time:
            filtered_events = [e for e in filtered_events if e.timestamp >= start_time]
        
        if end_time:
            filtered_events = [e for e in filtered_events if e.timestamp <= end_time]
        
        # Sort by timestamp (most recent first)
        filtered_events.sort(key=lambda x: x.timestamp, reverse=True)
        
        # Apply limit
        filtered_events = filtered_events[:limit]
        
        return [event.to_dict() for event in filtered_events]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get audit statistics"""
        with self._lock:
            stats = self.stats.copy()
        
        # Calculate additional metrics
        if self.events:
            # Success rate
            successful_events = len([e for e in self.events if e.success])
            stats["success_rate"] = (successful_events / len(self.events)) * 100
            
            # Average duration
            events_with_duration = [e for e in self.events if e.duration_ms is not None]
            if events_with_duration:
                stats["average_duration_ms"] = sum(e.duration_ms for e in events_with_duration) / len(events_with_duration)
            
            # Recent activity (last hour)
            one_hour_ago = datetime.now() - timedelta(hours=1)
            recent_events = [e for e in self.events if e.timestamp >= one_hour_ago]
            stats["events_last_hour"] = len(recent_events)
            
            # Most active users
            user_activity = {}
            for event in self.events:
                if event.user_id:
                    user_activity[event.user_id] = user_activity.get(event.user_id, 0) + 1
            
            stats["most_active_users"] = sorted(user_activity.items(), key=lambda x: x[1], reverse=True)[:10]
        else:
            stats["success_rate"] = 0
            stats["average_duration_ms"] = 0
            stats["events_last_hour"] = 0
            stats["most_active_users"] = []
        
        return stats
    
    def export_events(self, format: str = "json", start_time: Optional[datetime] = None,
                    end_time: Optional[datetime] = None, event_type: Optional[AuditEventType] = None,
                    user_id: Optional[str] = None) -> str:
        """Export audit events"""
        events = self.get_events(
            limit=10000,  # Large limit for export
            event_type=event_type,
            user_id=user_id,
            start_time=start_time,
            end_time=end_time
        )
        
        if format.lower() == "json":
            return json.dumps({
                "export_timestamp": datetime.now().isoformat(),
                "total_events": len(events),
                "events": events
            }, indent=2, default=str)
        
        elif format.lower() == "csv":
            import csv
            import io
            
            output = io.StringIO()
            if events:
                fieldnames = events[0].keys()
                writer = csv.DictWriter(output, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(events)
            
            return output.getvalue()
        
        else:
            raise ValueError(f"Unsupported export format: {format}")
    
    def search_events(self, query: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Search audit events"""
        with self._lock:
            matching_events = []
            
            query_lower = query.lower()
            
            for event in self.events:
                # Search in various fields
                searchable_text = " ".join([
                    event.action,
                    event.user_id or "",
                    event.server_id or "",
                    event.error_message or "",
                    json.dumps(event.details, default=str).lower()
                ]).lower()
                
                if query_lower in searchable_text:
                    matching_events.append(event.to_dict())
            
            # Sort by timestamp (most recent first)
            matching_events.sort(key=lambda x: x["timestamp"], reverse=True)
            
            return matching_events[:limit]
    
    def get_user_activity(self, user_id: str, days: int = 30) -> Dict[str, Any]:
        """Get user activity summary"""
        start_time = datetime.now() - timedelta(days=days)
        
        user_events = self.get_events(limit=10000, user_id=user_id, start_time=start_time)
        
        if not user_events:
            return {"user_id": user_id, "total_events": 0, "activity_period_days": days}
        
        # Analyze activity
        total_events = len(user_events)
        
        # Event type distribution
        event_types = {}
        for event in user_events:
            event_type = event["event_type"]
            event_types[event_type] = event_types.get(event_type, 0) + 1
        
        # Success rate
        successful_events = len([e for e in user_events if e["success"]])
        success_rate = (successful_events / total_events) * 100
        
        # Activity timeline
        daily_activity = {}
        for event in user_events:
            date = event["timestamp"][:10]  # YYYY-MM-DD
            daily_activity[date] = daily_activity.get(date, 0) + 1
        
        # Most recent activity
        most_recent = user_events[0]["timestamp"] if user_events else None
        
        return {
            "user_id": user_id,
            "total_events": total_events,
            "activity_period_days": days,
            "success_rate": round(success_rate, 2),
            "event_type_distribution": event_types,
            "daily_activity": daily_activity,
            "most_recent_activity": most_recent,
            "first_activity": user_events[-1]["timestamp"] if user_events else None
        }
    
    def get_security_report(self, days: int = 7) -> Dict[str, Any]:
        """Generate security report"""
        start_time = datetime.now() - timedelta(days=days)
        
        # Get security-related events
        security_events = []
        for event_type in [AuditEventType.SECURITY_VIOLATION, AuditEventType.USER_LOGIN]:
            events = self.get_events(limit=10000, event_type=event_type, start_time=start_time)
            security_events.extend(events)
        
        # Failed login attempts
        failed_logins = [
            e for e in security_events
            if e["event_type"] == AuditEventType.USER_LOGIN.value and not e["success"]
        ]
        
        # Unique source IPs
        source_ips = set()
        for event in security_events:
            if event.get("source_ip"):
                source_ips.add(event["source_ip"])
        
        # Suspicious activity patterns
        suspicious_patterns = {
            "multiple_failed_logins": len([e for e in failed_logins if e.get("details", {}).get("failed_attempts", 0) > 3]),
            "unusual_source_ips": len([ip for ip in source_ips if self._is_suspicious_ip(ip)]),
            "security_violations": len([e for e in security_events if e["event_type"] == AuditEventType.SECURITY_VIOLATION.value])
        }
        
        return {
            "report_period_days": days,
            "total_security_events": len(security_events),
            "failed_login_attempts": len(failed_logins),
            "unique_source_ips": len(source_ips),
            "suspicious_patterns": suspicious_patterns,
            "security_events": security_events,
            "recommendations": self._generate_security_recommendations(suspicious_patterns)
        }
    
    def _is_suspicious_ip(self, ip: str) -> bool:
        """Check if IP address is suspicious"""
        # Simple heuristics for suspicious IPs
        suspicious_indicators = [
            ip.startswith("10.0.0."),  # Private network (could be internal)
            ip.startswith("192.168."),  # Private network
            ip.startswith("172.16."),   # Private network
            ip.startswith("127.")      # Localhost
        ]
        
        # In a real implementation, you might check against threat intelligence feeds
        return not any(indicator for indicator in suspicious_indicators)
    
    def _generate_security_recommendations(self, patterns: Dict[str, int]) -> List[str]:
        """Generate security recommendations based on patterns"""
        recommendations = []
        
        if patterns["multiple_failed_logins"] > 0:
            recommendations.append("Consider implementing account lockout after multiple failed login attempts")
        
        if patterns["unusual_source_ips"] > 0:
            recommendations.append("Review access from unusual IP addresses and consider geolocation filtering")
        
        if patterns["security_violations"] > 0:
            recommendations.append("Investigate security violations and review access controls")
        
        if sum(patterns.values()) > 10:
            recommendations.append("Consider implementing additional security monitoring and alerting")
        
        return recommendations

# Global audit logger instance
audit_logger = AuditLogger()
