"""
Analytics and Reporting Engine for Dell Server AI Agent
"""

import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import statistics
from collections import defaultdict, Counter
import json

from models.server_models import ServerStatus, ComponentType, Severity, ActionLevel

logger = logging.getLogger(__name__)

class ReportType(str, Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    CUSTOM = "custom"

class MetricType(str, Enum):
    PERFORMANCE = "performance"
    AVAILABILITY = "availability"
    HEALTH = "health"
    MAINTENANCE = "maintenance"
    SECURITY = "security"
    COST = "cost"

@dataclass
class AnalyticsMetric:
    """Analytics metric definition"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    category: MetricType
    tags: Dict[str, str] = None

@dataclass
class Report:
    """Analytics report definition"""
    id: str
    name: str
    report_type: ReportType
    generated_at: datetime
    period_start: datetime
    period_end: datetime
    metrics: List[AnalyticsMetric]
    insights: List[str]
    recommendations: List[str]
    charts: List[Dict[str, Any]]

class AnalyticsEngine:
    """Analytics and reporting engine for server management"""
    
    def __init__(self):
        self.metrics_history: List[AnalyticsMetric] = []
        self.reports: List[Report] = []
        self.benchmarks: Dict[str, float] = self._initialize_benchmarks()
        self.alert_thresholds: Dict[str, Dict] = self._initialize_thresholds()
        
    def _initialize_benchmarks(self) -> Dict[str, float]:
        """Initialize industry benchmarks"""
        return {
            "availability_target": 99.9,  # %
            "avg_cpu_utilization": 65.0,  # %
            "avg_memory_utilization": 75.0,  # %
            "avg_temperature": 45.0,  # Celsius
            "mtbf_hours": 8760,  # Mean time between failures (1 year)
            "maintenance_interval_days": 30,
            "incident_response_time_minutes": 15,
            "patch_deployment_time_hours": 4
        }
    
    def _initialize_thresholds(self) -> Dict[str, Dict]:
        """Initialize alert thresholds"""
        return {
            "cpu_utilization": {
                "warning": 80.0,
                "critical": 95.0
            },
            "memory_utilization": {
                "warning": 85.0,
                "critical": 95.0
            },
            "temperature": {
                "warning": 70.0,
                "critical": 85.0
            },
            "availability": {
                "warning": 99.0,
                "critical": 97.0
            },
            "error_rate": {
                "warning": 0.02,  # 2%
                "critical": 0.05   # 5%
            }
        }
    
    def add_metric(self, name: str, value: float, unit: str, category: MetricType,
                   tags: Dict[str, str] = None, timestamp: Optional[datetime] = None):
        """Add a metric to the analytics engine"""
        metric = AnalyticsMetric(
            name=name,
            value=value,
            unit=unit,
            timestamp=timestamp or datetime.now(),
            category=category,
            tags=tags or {}
        )
        
        self.metrics_history.append(metric)
        
        # Keep only last 10000 metrics to prevent memory issues
        if len(self.metrics_history) > 10000:
            self.metrics_history = self.metrics_history[-10000:]
    
    def generate_report(self, report_type: ReportType, 
                       period_start: Optional[datetime] = None,
                       period_end: Optional[datetime] = None) -> Report:
        """Generate analytics report"""
        
        if period_start is None:
            if report_type == ReportType.DAILY:
                period_start = datetime.now() - timedelta(days=1)
            elif report_type == ReportType.WEEKLY:
                period_start = datetime.now() - timedelta(weeks=1)
            elif report_type == ReportType.MONTHLY:
                period_start = datetime.now() - timedelta(days=30)
            elif report_type == ReportType.QUARTERLY:
                period_start = datetime.now() - timedelta(days=90)
            else:
                period_start = datetime.now() - timedelta(days=7)
        
        if period_end is None:
            period_end = datetime.now()
        
        # Filter metrics for the period
        period_metrics = [
            m for m in self.metrics_history
            if period_start <= m.timestamp <= period_end
        ]
        
        # Generate report content
        metrics = self._calculate_report_metrics(period_metrics)
        insights = self._generate_insights(metrics, period_metrics)
        recommendations = self._generate_recommendations(insights, metrics)
        charts = self._generate_chart_data(metrics, period_start, period_end)
        
        report = Report(
            id=f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            name=f"{report_type.value.title()} Report",
            report_type=report_type,
            generated_at=datetime.now(),
            period_start=period_start,
            period_end=period_end,
            metrics=metrics,
            insights=insights,
            recommendations=recommendations,
            charts=charts
        )
        
        self.reports.append(report)
        
        logger.info(f"Generated {report_type.value} report with {len(metrics)} metrics")
        
        return report
    
    def _calculate_report_metrics(self, period_metrics: List[AnalyticsMetric]) -> List[AnalyticsMetric]:
        """Calculate aggregated metrics for the report"""
        calculated_metrics = []
        
        # Group metrics by name and calculate aggregates
        metric_groups = defaultdict(list)
        for metric in period_metrics:
            metric_groups[metric.name].append(metric.value)
        
        for metric_name, values in metric_groups.items():
            if not values:
                continue
            
            # Calculate statistics
            avg_value = statistics.mean(values)
            min_value = min(values)
            max_value = max(values)
            
            # Determine metric category and unit
            category = self._get_metric_category(metric_name)
            unit = self._get_metric_unit(metric_name)
            
            # Add aggregated metrics
            calculated_metrics.extend([
                AnalyticsMetric(
                    name=f"{metric_name}_average",
                    value=avg_value,
                    unit=unit,
                    timestamp=datetime.now(),
                    category=category
                ),
                AnalyticsMetric(
                    name=f"{metric_name}_minimum",
                    value=min_value,
                    unit=unit,
                    timestamp=datetime.now(),
                    category=category
                ),
                AnalyticsMetric(
                    name=f"{metric_name}_maximum",
                    value=max_value,
                    unit=unit,
                    timestamp=datetime.now(),
                    category=category
                )
            ])
        
        # Calculate derived metrics
        calculated_metrics.extend(self._calculate_derived_metrics(period_metrics))
        
        return calculated_metrics
    
    def _calculate_derived_metrics(self, period_metrics: List[AnalyticsMetric]) -> List[AnalyticsMetric]:
        """Calculate derived metrics from base metrics"""
        derived_metrics = []
        
        # Calculate availability percentage
        uptime_metrics = [m for m in period_metrics if m.name == "uptime_hours"]
        total_time_metrics = [m for m in period_metrics if m.name == "total_time_hours"]
        
        if uptime_metrics and total_time_metrics:
            total_uptime = sum(m.value for m in uptime_metrics)
            total_time = sum(m.value for m in total_time_metrics)
            
            if total_time > 0:
                availability = (total_uptime / total_time) * 100
                derived_metrics.append(AnalyticsMetric(
                    name="availability_percentage",
                    value=availability,
                    unit="%",
                    timestamp=datetime.now(),
                    category=MetricType.AVAILABILITY
                ))
        
        # Calculate error rate
        error_metrics = [m for m in period_metrics if m.name == "error_count"]
        total_request_metrics = [m for m in period_metrics if m.name == "total_requests"]
        
        if error_metrics and total_request_metrics:
            total_errors = sum(m.value for m in error_metrics)
            total_requests = sum(m.value for m in total_request_metrics)
            
            if total_requests > 0:
                error_rate = (total_errors / total_requests) * 100
                derived_metrics.append(AnalyticsMetric(
                    name="error_rate_percentage",
                    value=error_rate,
                    unit="%",
                    timestamp=datetime.now(),
                    category=MetricType.HEALTH
                ))
        
        # Calculate performance score
        performance_metrics = [m for m in period_metrics if m.category == MetricType.PERFORMANCE]
        if performance_metrics:
            # Simple performance score based on CPU, memory, and response time
            cpu_metrics = [m for m in performance_metrics if "cpu" in m.name.lower()]
            memory_metrics = [m for m in performance_metrics if "memory" in m.name.lower()]
            
            score = 100.0  # Start with perfect score
            
            # Deduct points for high utilization
            if cpu_metrics:
                avg_cpu = statistics.mean(m.value for m in cpu_metrics)
                if avg_cpu > 80:
                    score -= (avg_cpu - 80) * 2
            
            if memory_metrics:
                avg_memory = statistics.mean(m.value for m in memory_metrics)
                if avg_memory > 85:
                    score -= (avg_memory - 85) * 2
            
            derived_metrics.append(AnalyticsMetric(
                name="performance_score",
                value=max(0, score),
                unit="score",
                timestamp=datetime.now(),
                category=MetricType.PERFORMANCE
            ))
        
        return derived_metrics
    
    def _get_metric_category(self, metric_name: str) -> MetricType:
        """Determine metric category from name"""
        name_lower = metric_name.lower()
        
        if any(keyword in name_lower for keyword in ["cpu", "memory", "performance", "response"]):
            return MetricType.PERFORMANCE
        elif any(keyword in name_lower for keyword in ["uptime", "availability", "downtime"]):
            return MetricType.AVAILABILITY
        elif any(keyword in name_lower for keyword in ["health", "temperature", "error", "warning"]):
            return MetricType.HEALTH
        elif any(keyword in name_lower for keyword in ["maintenance", "repair", "service"]):
            return MetricType.MAINTENANCE
        elif any(keyword in name_lower for keyword in ["security", "auth", "login"]):
            return MetricType.SECURITY
        elif any(keyword in name_lower for keyword in ["cost", "budget", "expense"]):
            return MetricType.COST
        else:
            return MetricType.PERFORMANCE  # Default
    
    def _get_metric_unit(self, metric_name: str) -> str:
        """Determine metric unit from name"""
        name_lower = metric_name.lower()
        
        if "percentage" in name_lower or "utilization" in name_lower:
            return "%"
        elif "temperature" in name_lower:
            return "°C"
        elif "time" in name_lower or "response" in name_lower:
            return "ms"
        elif "hours" in name_lower:
            return "hours"
        elif "count" in name_lower:
            return "count"
        elif "score" in name_lower:
            return "score"
        else:
            return "units"
    
    def _generate_insights(self, metrics: List[AnalyticsMetric], 
                          period_metrics: List[AnalyticsMetric]) -> List[str]:
        """Generate insights from metrics"""
        insights = []
        
        # Performance insights
        cpu_metrics = [m for m in metrics if "cpu" in m.name.lower() and "average" in m.name.lower()]
        if cpu_metrics:
            avg_cpu = cpu_metrics[0].value
            if avg_cpu > 80:
                insights.append(f"High CPU utilization detected at {avg_cpu:.1f}%. Consider workload optimization or capacity upgrade.")
            elif avg_cpu < 30:
                insights.append(f"Low CPU utilization at {avg_cpu:.1f}%. Resources may be underutilized.")
        
        # Memory insights
        memory_metrics = [m for m in metrics if "memory" in m.name.lower() and "average" in m.name.lower()]
        if memory_metrics:
            avg_memory = memory_metrics[0].value
            if avg_memory > 85:
                insights.append(f"High memory utilization at {avg_memory:.1f}%. Monitor for memory leaks or consider upgrade.")
        
        # Temperature insights
        temp_metrics = [m for m in metrics if "temperature" in m.name.lower() and "average" in m.name.lower()]
        if temp_metrics:
            avg_temp = temp_metrics[0].value
            if avg_temp > 70:
                insights.append(f"Elevated temperatures at {avg_temp:.1f}°C. Check cooling systems and airflow.")
        
        # Availability insights
        availability_metrics = [m for m in metrics if "availability" in m.name.lower()]
        if availability_metrics:
            availability = availability_metrics[0].value
            target = self.benchmarks["availability_target"]
            if availability < target:
                insights.append(f"Availability at {availability:.2f}% is below target of {target}%. Review uptime incidents.")
        
        # Error rate insights
        error_metrics = [m for m in metrics if "error_rate" in m.name.lower()]
        if error_metrics:
            error_rate = error_metrics[0].value
            if error_rate > 2.0:  # 2%
                insights.append(f"Error rate at {error_rate:.2f}% is elevated. Investigate error patterns and root causes.")
        
        # Trend insights
        insights.extend(self._generate_trend_insights(period_metrics))
        
        return insights
    
    def _generate_trend_insights(self, period_metrics: List[AnalyticsMetric]) -> List[str]:
        """Generate trend-based insights"""
        insights = []
        
        # Group metrics by name and analyze trends
        metric_groups = defaultdict(list)
        for metric in period_metrics:
            metric_groups[metric.name].append(metric)
        
        for metric_name, metrics_list in metric_groups.items():
            if len(metrics_list) < 5:  # Need sufficient data points
                continue
            
            # Sort by timestamp
            metrics_list.sort(key=lambda x: x.timestamp)
            
            # Calculate trend
            values = [m.value for m in metrics_list]
            if len(values) >= 3:
                # Simple linear regression for trend
                n = len(values)
                x = list(range(n))
                sum_x = sum(x)
                sum_y = sum(values)
                sum_xy = sum(x[i] * values[i] for i in range(n))
                sum_x2 = sum(x[i] ** 2 for i in range(n))
                
                if n * sum_x2 - sum_x ** 2 != 0:
                    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
                    
                    # Generate insight based on trend
                    if abs(slope) > 0.1:  # Significant trend
                        direction = "increasing" if slope > 0 else "decreasing"
                        insights.append(f"{metric_name.replace('_', ' ').title()} shows {direction} trend over the period.")
        
        return insights
    
    def _generate_recommendations(self, insights: List[str], 
                                metrics: List[AnalyticsMetric]) -> List[str]:
        """Generate recommendations based on insights and metrics"""
        recommendations = []
        
        # Performance recommendations
        cpu_metrics = [m for m in metrics if "cpu" in m.name.lower() and "average" in m.name.lower()]
        if cpu_metrics and cpu_metrics[0].value > 80:
            recommendations.append("Optimize workloads or upgrade CPU capacity to reduce utilization.")
        
        memory_metrics = [m for m in metrics if "memory" in m.name.lower() and "average" in m.name.lower()]
        if memory_metrics and memory_metrics[0].value > 85:
            recommendations.append("Investigate memory usage patterns and consider memory upgrade.")
        
        # Availability recommendations
        availability_metrics = [m for m in metrics if "availability" in m.name.lower()]
        if availability_metrics and availability_metrics[0].value < 99.0:
            recommendations.append("Implement redundancy and improve monitoring to increase availability.")
        
        # Temperature recommendations
        temp_metrics = [m for m in metrics if "temperature" in m.name.lower() and "average" in m.name.lower()]
        if temp_metrics and temp_metrics[0].value > 70:
            recommendations.append("Schedule cooling system maintenance and improve airflow.")
        
        # General recommendations based on insights
        if any("high" in insight.lower() for insight in insights):
            recommendations.append("Review system performance and consider capacity planning.")
        
        if any("elevated" in insight.lower() or "error" in insight.lower() for insight in insights):
            recommendations.append("Implement proactive monitoring and alerting for early issue detection.")
        
        return recommendations
    
    def _generate_chart_data(self, metrics: List[AnalyticsMetric], 
                           period_start: datetime, period_end: datetime) -> List[Dict[str, Any]]:
        """Generate chart data for visualization"""
        charts = []
        
        # Time series chart for CPU utilization
        cpu_metrics = [m for m in metrics if "cpu" in m.name.lower()]
        if cpu_metrics:
            charts.append({
                "type": "timeseries",
                "title": "CPU Utilization Over Time",
                "data": [
                    {
                        "timestamp": m.timestamp.isoformat(),
                        "value": m.value,
                        "metric": m.name
                    }
                    for m in cpu_metrics
                ],
                "x_axis": "timestamp",
                "y_axis": "value",
                "unit": "%"
            })
        
        # Pie chart for metric distribution
        metric_categories = Counter(m.category for m in metrics)
        if metric_categories:
            charts.append({
                "type": "pie",
                "title": "Metrics by Category",
                "data": [
                    {
                        "category": category.value,
                        "count": count
                    }
                    for category, count in metric_categories.items()
                ]
            })
        
        # Bar chart for current vs benchmark
        benchmark_metrics = []
        for metric_name, benchmark_value in self.benchmarks.items():
            current_metrics = [m for m in metrics if metric_name in m.name.lower() and "average" in m.name.lower()]
            if current_metrics:
                benchmark_metrics.append({
                    "metric": metric_name.replace("_", " ").title(),
                    "current": current_metrics[0].value,
                    "benchmark": benchmark_value
                })
        
        if benchmark_metrics:
            charts.append({
                "type": "bar",
                "title": "Current vs Benchmark Performance",
                "data": benchmark_metrics,
                "x_axis": "metric",
                "y_axis": ["current", "benchmark"]
            })
        
        return charts
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Get data for dashboard visualization"""
        now = datetime.now()
        last_24h = now - timedelta(hours=24)
        last_7d = now - timedelta(days=7)
        
        # Recent metrics
        recent_metrics = [m for m in self.metrics_history if m.timestamp >= last_24h]
        
        # Calculate key metrics
        key_metrics = {}
        
        # Availability
        availability_metrics = [m for m in recent_metrics if "availability" in m.name.lower()]
        if availability_metrics:
            key_metrics["availability"] = statistics.mean(m.value for m in availability_metrics)
        
        # Performance score
        performance_metrics = [m for m in recent_metrics if "performance_score" in m.name.lower()]
        if performance_metrics:
            key_metrics["performance_score"] = performance_metrics[-1].value
        
        # Error rate
        error_metrics = [m for m in recent_metrics if "error_rate" in m.name.lower()]
        if error_metrics:
            key_metrics["error_rate"] = error_metrics[-1].value
        
        # System health
        health_metrics = [m for m in recent_metrics if m.category == MetricType.HEALTH]
        if health_metrics:
            # Simple health calculation
            key_metrics["health_score"] = min(100, max(0, 100 - (key_metrics.get("error_rate", 0) * 10)))
        
        # Alerts
        alerts = self._check_alerts(recent_metrics)
        
        # Recent activity
        recent_activity = [
            {
                "timestamp": m.timestamp.isoformat(),
                "metric": m.name,
                "value": m.value,
                "category": m.category.value
            }
            for m in recent_metrics[-10:]  # Last 10 metrics
        ]
        
        return {
            "key_metrics": key_metrics,
            "alerts": alerts,
            "recent_activity": recent_activity,
            "total_metrics": len(recent_metrics),
            "last_updated": now.isoformat()
        }
    
    def _check_alerts(self, metrics: List[AnalyticsMetric]) -> List[Dict[str, Any]]:
        """Check for alert conditions"""
        alerts = []
        
        for metric in metrics:
            threshold_config = self.alert_thresholds.get(metric.name)
            if not threshold_config:
                continue
            
            if metric.value >= threshold_config.get("critical", float('inf')):
                alerts.append({
                    "level": "critical",
                    "metric": metric.name,
                    "value": metric.value,
                    "threshold": threshold_config["critical"],
                    "timestamp": metric.timestamp.isoformat(),
                    "message": f"Critical threshold exceeded for {metric.name}"
                })
            elif metric.value >= threshold_config.get("warning", float('inf')):
                alerts.append({
                    "level": "warning",
                    "metric": metric.name,
                    "value": metric.value,
                    "threshold": threshold_config["warning"],
                    "timestamp": metric.timestamp.isoformat(),
                    "message": f"Warning threshold exceeded for {metric.name}"
                })
        
        return sorted(alerts, key=lambda x: x["timestamp"], reverse=True)
    
    def get_metrics_history(self, metric_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Get historical data for a specific metric"""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        filtered_metrics = [
            m for m in self.metrics_history
            if m.name == metric_name and m.timestamp >= cutoff_time
        ]
        
        return [
            {
                "timestamp": m.timestamp.isoformat(),
                "value": m.value,
                "unit": m.unit
            }
            for m in sorted(filtered_metrics, key=lambda x: x.timestamp)
        ]
    
    def export_report(self, report_id: str, format: str = "json") -> Dict[str, Any]:
        """Export report in specified format"""
        report = next((r for r in self.reports if r.id == report_id), None)
        if not report:
            return {"error": "Report not found"}
        
        if format == "json":
            return {
                "report": {
                    "id": report.id,
                    "name": report.name,
                    "type": report.report_type.value,
                    "generated_at": report.generated_at.isoformat(),
                    "period": {
                        "start": report.period_start.isoformat(),
                        "end": report.period_end.isoformat()
                    },
                    "metrics": [
                        {
                            "name": m.name,
                            "value": m.value,
                            "unit": m.unit,
                            "category": m.category.value,
                            "timestamp": m.timestamp.isoformat()
                        }
                        for m in report.metrics
                    ],
                    "insights": report.insights,
                    "recommendations": report.recommendations,
                    "charts": report.charts
                }
            }
        
        elif format == "csv":
            # Simple CSV export for metrics
            csv_data = "Metric Name,Value,Unit,Category,Timestamp\n"
            for m in report.metrics:
                csv_data += f"{m.name},{m.value},{m.unit},{m.category.value},{m.timestamp.isoformat()}\n"
            
            return {"csv": csv_data}
        
        else:
            return {"error": "Unsupported format"}
    
    def get_reports_list(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get list of generated reports"""
        reports = sorted(self.reports, key=lambda x: x.generated_at, reverse=True)
        
        return [
            {
                "id": r.id,
                "name": r.name,
                "type": r.report_type.value,
                "generated_at": r.generated_at.isoformat(),
                "period_start": r.period_start.isoformat(),
                "period_end": r.period_end.isoformat(),
                "metrics_count": len(r.metrics),
                "insights_count": len(r.insights)
            }
            for r in reports[:limit]
        ]
