"""
AI-powered log analysis for Dell servers
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import re
from collections import Counter, defaultdict

from core.config import AgentConfig
from models.server_models import LogEntry, Severity, ComponentType

logger = logging.getLogger(__name__)

class LogAnalyzer:
    """AI engine for analyzing server logs and identifying patterns"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        
        # Common error patterns and their meanings
        self.error_patterns = {
            "memory_errors": [
                r"memory.*error",
                r"ecc.*error",
                r"dim.*error",
                r"correctable.*error",
                r"uncorrectable.*error"
            ],
            "power_errors": [
                r"power.*fail",
                r"psu.*error",
                r"power.*supply",
                r"voltage.*error",
                r"power.*loss"
            ],
            "temperature_errors": [
                r"temperature.*critical",
                r"over.*temp",
                r"thermal.*error",
                r"fan.*fail",
                r"cooling.*error"
            ],
            "storage_errors": [
                r"disk.*error",
                r"drive.*fail",
                r"raid.*error",
                r"controller.*error",
                r"smart.*error"
            ],
            "network_errors": [
                r"network.*error",
                r"link.*down",
                r"nic.*error",
                r"connectivity.*lost",
                r"ethernet.*error"
            ],
            "firmware_errors": [
                r"firmware.*error",
                r"bios.*error",
                r"idrac.*error",
                r"update.*fail",
                r"flash.*error"
            ]
        }
        
        # Severity keywords
        self.severity_keywords = {
            Severity.CRITICAL: ["critical", "fatal", "emergency", "alert"],
            Severity.ERROR: ["error", "fail", "failure", "exception"],
            Severity.WARNING: ["warning", "warn", "caution", "degraded"],
            Severity.INFO: ["info", "information", "notice", "normal"]
        }
    
    async def analyze_logs(self, logs: List[LogEntry], time_window: Optional[timedelta] = None) -> Dict[str, Any]:
        """Analyze logs and provide insights"""
        
        if not logs:
            return {"status": "no_logs", "analysis": {}}
        
        # Filter logs by time window if specified
        if time_window:
            cutoff_time = datetime.now() - time_window
            logs = [log for log in logs if log.timestamp >= cutoff_time]
        
        analysis = {
            "summary": self._generate_summary(logs),
            "patterns": self._identify_patterns(logs),
            "trends": self._analyze_trends(logs),
            "recommendations": self._generate_log_recommendations(logs),
            "critical_events": self._extract_critical_events(logs)
        }
        
        return {"status": "success", "analysis": analysis}
    
    def _generate_summary(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Generate a summary of log statistics"""
        
        total_logs = len(logs)
        severity_counts = Counter(log.severity for log in logs)
        component_counts = Counter(log.component for log in logs)
        
        # Time range
        timestamps = [log.timestamp for log in logs]
        time_range = {
            "start": min(timestamps) if timestamps else None,
            "end": max(timestamps) if timestamps else None,
            "duration_hours": (max(timestamps) - min(timestamps)).total_seconds() / 3600 if timestamps else 0
        }
        
        # Most frequent sources
        source_counts = Counter(log.source for log in logs if log.source)
        
        return {
            "total_logs": total_logs,
            "severity_distribution": {k.value: v for k, v in severity_counts.items()},
            "component_distribution": {k.value: v for k, v in component_counts.items()},
            "time_range": time_range,
            "most_frequent_sources": dict(source_counts.most_common(5)),
            "logs_per_hour": total_logs / max(time_range["duration_hours"], 1)
        }
    
    def _identify_patterns(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Identify common patterns in logs"""
        
        patterns = {
            "error_categories": defaultdict(list),
            "recurring_messages": defaultdict(int),
            "time_correlations": []
        }
        
        # Categorize errors
        for log in logs:
            message_lower = log.message.lower()
            
            for category, regex_patterns in self.error_patterns.items():
                for pattern in regex_patterns:
                    if re.search(pattern, message_lower, re.IGNORECASE):
                        patterns["error_categories"][category].append(log)
                        break
        
        # Find recurring messages
        message_counts = Counter(log.message for log in logs)
        patterns["recurring_messages"] = dict(message_counts.most_common(10))
        
        # Look for time correlations (multiple events in short time)
        time_groups = defaultdict(list)
        for log in logs:
            # Group by hour
            hour_key = log.timestamp.replace(minute=0, second=0, microsecond=0)
            time_groups[hour_key].append(log)
        
        # Find hours with unusual activity
        hourly_counts = {hour: len(logs) for hour, logs in time_groups.items()}
        if hourly_counts:
            avg_hourly = sum(hourly_counts.values()) / len(hourly_counts)
            patterns["time_correlations"] = [
                {"hour": str(hour), "count": count, "ratio": count/avg_hourly}
                for hour, count in hourly_counts.items()
                if count > avg_hourly * 2  # More than 2x average
            ]
        
        return patterns
    
    def _analyze_trends(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Analyze trends in log data"""
        
        if not logs:
            return {}
        
        # Sort logs by timestamp
        sorted_logs = sorted(logs, key=lambda x: x.timestamp)
        
        # Group by time periods (hours)
        hourly_data = defaultdict(lambda: {"total": 0, "severities": Counter()})
        
        for log in sorted_logs:
            hour_key = log.timestamp.replace(minute=0, second=0, microsecond=0)
            hourly_data[hour_key]["total"] += 1
            hourly_data[hour_key]["severities"][log.severity] += 1
        
        # Calculate trends
        hours = sorted(hourly_data.keys())
        if len(hours) < 2:
            return {"message": "Insufficient data for trend analysis"}
        
        # Severity trends
        severity_trends = {}
        for severity in Severity:
            counts = [hourly_data[hour]["severities"][severity] for hour in hours]
            if len(counts) >= 2:
                # Simple trend calculation (last vs first)
                trend = (counts[-1] - counts[0]) / max(counts[0], 1)
                severity_trends[severity.value] = {
                    "trend": "increasing" if trend > 0.1 else "decreasing" if trend < -0.1 else "stable",
                    "change_percent": round(trend * 100, 2)
                }
        
        # Overall volume trend
        total_counts = [hourly_data[hour]["total"] for hour in hours]
        volume_trend = (total_counts[-1] - total_counts[0]) / max(total_counts[0], 1)
        
        return {
            "severity_trends": severity_trends,
            "volume_trend": {
                "direction": "increasing" if volume_trend > 0.1 else "decreasing" if volume_trend < -0.1 else "stable",
                "change_percent": round(volume_trend * 100, 2)
            },
            "data_points": len(hours)
        }
    
    def _generate_log_recommendations(self, logs: List[LogEntry]) -> List[Dict[str, Any]]:
        """Generate recommendations based on log analysis"""
        
        recommendations = []
        
        # Check for high error rate
        error_logs = [log for log in logs if log.severity in [Severity.ERROR, Severity.CRITICAL]]
        if len(error_logs) > len(logs) * 0.1:  # More than 10% errors
            recommendations.append({
                "type": "high_error_rate",
                "priority": "high",
                "message": f"High error rate detected: {len(error_logs)} errors out of {len(logs)} logs",
                "action": "Investigate root cause of frequent errors"
            })
        
        # Check for recurring critical errors
        critical_messages = [log.message for log in logs if log.severity == Severity.CRITICAL]
        if critical_messages:
            message_counts = Counter(critical_messages)
            recurring_critical = [msg for msg, count in message_counts.items() if count > 1]
            
            if recurring_critical:
                recommendations.append({
                    "type": "recurring_critical",
                    "priority": "critical",
                    "message": f"Found {len(recurring_critical)} recurring critical error messages",
                    "action": "Address recurring critical errors immediately"
                })
        
        # Check for component-specific issues
        component_errors = defaultdict(int)
        for log in logs:
            if log.severity in [Severity.ERROR, Severity.CRITICAL]:
                component_errors[log.component] += 1
        
        for component, count in component_errors.items():
            if count > 5:  # More than 5 errors for a component
                recommendations.append({
                    "type": "component_issues",
                    "priority": "medium",
                    "message": f"Component {component.value} has {count} errors",
                    "action": f"Investigate {component.value} component health"
                })
        
        # Check for recent spikes
        recent_logs = [log for log in logs if log.timestamp >= datetime.now() - timedelta(hours=1)]
        if len(recent_logs) > 50:  # More than 50 logs in last hour
            recommendations.append({
                "type": "log_spike",
                "priority": "medium",
                "message": f"High log volume detected: {len(recent_logs)} logs in the last hour",
                "action": "Monitor system for potential issues causing increased logging"
            })
        
        return recommendations
    
    def _extract_critical_events(self, logs: List[LogEntry]) -> List[Dict[str, Any]]:
        """Extract and categorize critical events"""
        
        critical_events = []
        
        for log in logs:
            if log.severity == Severity.CRITICAL:
                event = {
                    "timestamp": log.timestamp.isoformat(),
                    "message": log.message,
                    "source": log.source,
                    "component": log.component.value if log.component else None,
                    "event_id": log.event_id
                }
                
                # Categorize the critical event
                message_lower = log.message.lower()
                category = "unknown"
                
                for cat_name, patterns in self.error_patterns.items():
                    for pattern in patterns:
                        if re.search(pattern, message_lower, re.IGNORECASE):
                            category = cat_name
                            break
                    if category != "unknown":
                        break
                
                event["category"] = category
                critical_events.append(event)
        
        # Sort by timestamp (most recent first)
        critical_events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return critical_events[:20]  # Return top 20 critical events
    
    async def search_logs(
        self, 
        logs: List[LogEntry], 
        query: str, 
        severity_filter: Optional[List[Severity]] = None,
        component_filter: Optional[List[ComponentType]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> List[LogEntry]:
        """Search logs with filters"""
        
        filtered_logs = logs
        
        # Apply severity filter
        if severity_filter:
            filtered_logs = [log for log in filtered_logs if log.severity in severity_filter]
        
        # Apply component filter
        if component_filter:
            filtered_logs = [log for log in filtered_logs if log.component in component_filter]
        
        # Apply time range filter
        if time_range:
            start_time, end_time = time_range
            filtered_logs = [log for log in filtered_logs 
                           if start_time <= log.timestamp <= end_time]
        
        # Apply text search
        if query:
            query_lower = query.lower()
            filtered_logs = [log for log in filtered_logs 
                           if query_lower in log.message.lower() or
                           (log.source and query_lower in log.source.lower())]
        
        # Sort by timestamp (most recent first)
        filtered_logs.sort(key=lambda x: x.timestamp, reverse=True)
        
        return filtered_logs
    
    def get_log_statistics(self, logs: List[LogEntry]) -> Dict[str, Any]:
        """Get detailed statistics about logs"""
        
        if not logs:
            return {"message": "No logs available"}
        
        # Basic counts
        total_logs = len(logs)
        severity_counts = Counter(log.severity for log in logs)
        component_counts = Counter(log.component for log in logs)
        source_counts = Counter(log.source for log in logs if log.source)
        
        # Time analysis
        timestamps = [log.timestamp for log in logs]
        time_span = max(timestamps) - min(timestamps) if timestamps else timedelta(0)
        
        # Hourly distribution
        hourly_dist = Counter(log.timestamp.hour for log in logs)
        
        # Daily distribution
        daily_dist = Counter(log.timestamp.date() for log in logs)
        
        return {
            "total_logs": total_logs,
            "time_span_hours": time_span.total_seconds() / 3600,
            "severity_breakdown": {k.value: v for k, v in severity_counts.items()},
            "component_breakdown": {k.value: v for k, v in component_counts.items()},
            "source_breakdown": dict(source_counts.most_common(10)),
            "hourly_distribution": dict(hourly_dist),
            "daily_distribution": {str(k): v for k, v in daily_dist.items()},
            "logs_per_hour": total_logs / max(time_span.total_seconds() / 3600, 1)
        }
