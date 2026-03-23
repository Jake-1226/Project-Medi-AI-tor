"""
Advanced Analytics Dashboard
Provides comprehensive analytics, insights, and reporting capabilities
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import json
from collections import defaultdict, deque
import statistics
import math

logger = logging.getLogger(__name__)

class MetricType(Enum):
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    TREND = "trend"

class InsightType(Enum):
    ANOMALY = "anomaly"
    TREND = "trend"
    CORRELATION = "correlation"
    PREDICTION = "prediction"
    OPTIMIZATION = "optimization"

@dataclass
class AnalyticsMetric:
    """Analytics metric definition"""
    name: str
    metric_type: MetricType
    description: str
    unit: str
    tags: Dict[str, str] = field(default_factory=dict)
    aggregation_method: str = "avg"  # avg, sum, min, max, p50, p95, p99
    
@dataclass
class Insight:
    """Analytics insight"""
    id: str
    insight_type: InsightType
    title: str
    description: str
    confidence: float  # 0.0 to 1.0
    impact: str  # low, medium, high, critical
    metrics_involved: List[str]
    details: Dict[str, Any]
    recommendations: List[str]
    generated_at: datetime
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "insight_type": self.insight_type.value,
            "title": self.title,
            "description": self.description,
            "confidence": self.confidence,
            "impact": self.impact,
            "metrics_involved": self.metrics_involved,
            "details": self.details,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None
        }

class AnomalyDetector:
    """Statistical anomaly detection"""
    
    def __init__(self, window_size: int = 100, sensitivity: float = 2.0):
        self.window_size = window_size
        self.sensitivity = sensitivity  # Standard deviations
        self.metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=window_size))
    
    def add_sample(self, metric_name: str, value: float, timestamp: datetime):
        """Add new sample to history"""
        self.metric_history[metric_name].append((timestamp, value))
    
    def detect_anomaly(self, metric_name: str, current_value: float) -> Tuple[bool, float, Dict]:
        """Detect if current value is anomalous"""
        history = self.metric_history[metric_name]
        
        if len(history) < 10:
            return False, 0.0, {"reason": "insufficient_history"}
        
        # Extract values
        values = [v for _, v in history]
        
        # Calculate statistics
        mean = statistics.mean(values)
        std_dev = statistics.stdev(values) if len(values) > 1 else 0
        
        if std_dev == 0:
            return False, 0.0, {"reason": "no_variance"}
        
        # Calculate Z-score
        z_score = abs((current_value - mean) / std_dev)
        
        is_anomaly = z_score > self.sensitivity
        
        return is_anomaly, z_score, {
            "mean": mean,
            "std_dev": std_dev,
            "z_score": z_score,
            "threshold": self.sensitivity
        }

class TrendAnalyzer:
    """Trend analysis and prediction"""
    
    def __init__(self, min_points: int = 5):
        self.min_points = min_points
        self.metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
    
    def add_sample(self, metric_name: str, value: float, timestamp: datetime):
        """Add new sample to history"""
        self.metric_history[metric_name].append((timestamp, value))
    
    def analyze_trend(self, metric_name: str, hours: int = 24) -> Dict[str, Any]:
        """Analyze trend for metric over specified hours"""
        history = self.metric_history[metric_name]
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Filter recent data
        recent_data = [(t, v) for t, v in history if t >= cutoff_time]
        
        if len(recent_data) < self.min_points:
            return {
                "trend": "insufficient_data",
                "slope": 0.0,
                "correlation": 0.0,
                "confidence": 0.0,
                "prediction": None
            }
        
        # Extract timestamps and values
        timestamps = [(t - recent_data[0][0]).total_seconds() / 3600 for t, _ in recent_data]  # Hours since start
        values = [v for _, v in recent_data]
        
        # Linear regression
        slope, correlation = self._linear_regression(timestamps, values)
        
        # Determine trend direction
        if abs(slope) < 0.01:
            trend = "stable"
        elif slope > 0:
            trend = "increasing"
        else:
            trend = "decreasing"
        
        # Calculate confidence based on correlation
        confidence = abs(correlation)
        
        # Make prediction
        prediction = None
        if confidence > 0.5:
            next_hour = timestamps[-1] + 1
            prediction = values[-1] + slope * 1
        
        return {
            "trend": trend,
            "slope": slope,
            "correlation": correlation,
            "confidence": confidence,
            "prediction": prediction,
            "data_points": len(recent_data),
            "time_range_hours": hours
        }
    
    def _linear_regression(self, x: List[float], y: List[float]) -> Tuple[float, float]:
        """Simple linear regression"""
        n = len(x)
        if n < 2:
            return 0.0, 0.0
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] * x[i] for i in range(n))
        
        # Calculate slope and correlation
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0, 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        
        # Calculate correlation coefficient
        mean_x = sum_x / n
        mean_y = sum_y / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denominator = math.sqrt(sum_sq_x * sum_sq_y)
        if denominator == 0:
            correlation = 0.0
        else:
            correlation = numerator / denominator
        
        return slope, correlation

class CorrelationAnalyzer:
    """Correlation analysis between metrics"""
    
    def __init__(self, min_correlation: float = 0.7):
        self.min_correlation = min_correlation
        self.metric_history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
    
    def add_sample(self, metric_name: str, value: float, timestamp: datetime):
        """Add new sample to history"""
        self.metric_history[metric_name].append((timestamp, value))
    
    def find_correlations(self, metric_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        """Find correlations between metric and others"""
        correlations = []
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        # Get data for target metric
        target_data = [(t, v) for t, v in self.metric_history[metric_name] if t >= cutoff_time]
        
        if len(target_data) < 10:
            return correlations
        
        target_values = [v for _, v in target_data]
        
        # Check against all other metrics
        for other_metric in self.metric_history:
            if other_metric == metric_name:
                continue
            
            other_data = [(t, v) for t, v in self.metric_history[other_metric] if t >= cutoff_time]
            
            if len(other_data) < 10:
                continue
            
            # Align data by timestamp (simplified - assumes same timestamps)
            other_values = [v for _, v in other_data]
            
            if len(target_values) != len(other_values):
                continue
            
            # Calculate correlation
            correlation = self._calculate_correlation(target_values, other_values)
            
            if abs(correlation) >= self.min_correlation:
                correlations.append({
                    "metric": other_metric,
                    "correlation": correlation,
                    "strength": "strong" if abs(correlation) >= 0.8 else "moderate",
                    "direction": "positive" if correlation > 0 else "negative"
                })
        
        # Sort by absolute correlation
        correlations.sort(key=lambda x: abs(x["correlation"]), reverse=True)
        
        return correlations
    
    def _calculate_correlation(self, x: List[float], y: List[float]) -> float:
        """Calculate Pearson correlation coefficient"""
        n = len(x)
        if n < 2:
            return 0.0
        
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        
        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        sum_sq_x = sum((x[i] - mean_x) ** 2 for i in range(n))
        sum_sq_y = sum((y[i] - mean_y) ** 2 for i in range(n))
        
        denominator = math.sqrt(sum_sq_x * sum_sq_y)
        if denominator == 0:
            return 0.0
        
        return numerator / denominator

class PerformanceOptimizer:
    """Performance optimization recommendations"""
    
    def __init__(self):
        self.optimization_rules = self._setup_optimization_rules()
    
    def _setup_optimization_rules(self) -> List[Dict]:
        """Setup optimization rules"""
        return [
            {
                "name": "high_fan_speed_optimization",
                "condition": {"metric": "avg_fan_speed", "operator": ">", "value": 8000},
                "recommendation": "Consider cleaning air filters or checking for airflow obstructions",
                "impact": "medium",
                "category": "thermal"
            },
            {
                "name": "power_efficiency_optimization",
                "condition": {"metric": "power_efficiency", "operator": "<", "value": 75},
                "recommendation": "Optimize power management settings or consider workload redistribution",
                "impact": "high",
                "category": "power"
            },
            {
                "name": "temperature_optimization",
                "condition": {"metric": "max_temp", "operator": ">", "value": 75},
                "recommendation": "Review cooling system and consider environmental temperature adjustments",
                "impact": "high",
                "category": "thermal"
            },
            {
                "name": "memory_utilization_optimization",
                "condition": {"metric": "memory_health", "operator": "<", "value": 85},
                "recommendation": "Check for memory leaks or consider memory upgrade",
                "impact": "medium",
                "category": "memory"
            }
        ]
    
    def generate_recommendations(self, metrics: Dict[str, Any]) -> List[Dict]:
        """Generate optimization recommendations"""
        recommendations = []
        
        for rule in self.optimization_rules:
            metric_name = rule["condition"]["metric"]
            
            if metric_name not in metrics:
                continue
            
            current_value = metrics[metric_name].get("current_value", 0)
            operator = rule["condition"]["operator"]
            threshold = rule["condition"]["value"]
            
            if self._check_condition(current_value, operator, threshold):
                recommendations.append({
                    "rule": rule["name"],
                    "category": rule["category"],
                    "recommendation": rule["recommendation"],
                    "impact": rule["impact"],
                    "metric": metric_name,
                    "current_value": current_value,
                    "threshold": threshold,
                    "priority": self._calculate_priority(rule["impact"], current_value, threshold)
                })
        
        # Sort by priority
        recommendations.sort(key=lambda x: x["priority"], reverse=True)
        
        return recommendations
    
    def _check_condition(self, value: float, operator: str, threshold: float) -> bool:
        """Check if condition is met"""
        if operator == ">":
            return value > threshold
        elif operator == "<":
            return value < threshold
        elif operator == ">=":
            return value >= threshold
        elif operator == "<=":
            return value <= threshold
        else:
            return False
    
    def _calculate_priority(self, impact: str, current_value: float, threshold: float) -> float:
        """Calculate recommendation priority score"""
        impact_scores = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        base_score = impact_scores.get(impact, 1)
        
        # Add urgency based on how far from threshold
        deviation = abs(current_value - threshold) / threshold
        urgency_score = min(deviation * 2, 3)  # Cap at 3
        
        return base_score + urgency_score

class AnalyticsDashboard:
    """Main analytics dashboard system"""
    
    def __init__(self):
        self.metrics: Dict[str, AnalyticsMetric] = {}
        self.insights: deque = deque(maxlen=1000)
        self.anomaly_detector = AnomalyDetector()
        self.trend_analyzer = TrendAnalyzer()
        self.correlation_analyzer = CorrelationAnalyzer()
        self.performance_optimizer = PerformanceOptimizer()
        
        # Setup default metrics
        self._setup_default_metrics()
    
    def _setup_default_metrics(self):
        """Setup default analytics metrics"""
        default_metrics = [
            AnalyticsMetric("inlet_temp", MetricType.GAUGE, "Inlet Temperature", "°C"),
            AnalyticsMetric("cpu_temp", MetricType.GAUGE, "CPU Temperature", "°C"),
            AnalyticsMetric("max_temp", MetricType.GAUGE, "Maximum Temperature", "°C"),
            AnalyticsMetric("avg_fan_speed", MetricType.GAUGE, "Average Fan Speed", "RPM"),
            AnalyticsMetric("power_consumption", MetricType.GAUGE, "Power Consumption", "W"),
            AnalyticsMetric("power_efficiency", MetricType.GAUGE, "Power Efficiency", "%"),
            AnalyticsMetric("memory_health", MetricType.GAUGE, "Memory Health", "%"),
            AnalyticsMetric("storage_health", MetricType.GAUGE, "Storage Health", "%"),
            AnalyticsMetric("overall_health", MetricType.GAUGE, "Overall Health", "%"),
        ]
        
        for metric in default_metrics:
            self.metrics[metric.name] = metric
    
    async def process_metrics(self, metrics_data: Dict[str, Any]):
        """Process new metrics data and generate insights"""
        timestamp = datetime.now()
        
        # Update analyzers
        for metric_name, metric_data in metrics_data.items():
            if metric_name in self.metrics:
                current_value = metric_data.get("current_value", 0)
                
                # Add to all analyzers
                self.anomaly_detector.add_sample(metric_name, current_value, timestamp)
                self.trend_analyzer.add_sample(metric_name, current_value, timestamp)
                self.correlation_analyzer.add_sample(metric_name, current_value, timestamp)
        
        # Generate insights
        await self._generate_insights(metrics_data)
        
        # Clean up old insights
        self._cleanup_old_insights()
    
    async def _generate_insights(self, metrics_data: Dict[str, Any]):
        """Generate various types of insights"""
        # Anomaly detection
        await self._generate_anomaly_insights(metrics_data)
        
        # Trend analysis
        await self._generate_trend_insights(metrics_data)
        
        # Correlation analysis
        await self._generate_correlation_insights(metrics_data)
        
        # Performance optimization
        await self._generate_optimization_insights(metrics_data)
    
    async def _generate_anomaly_insights(self, metrics_data: Dict[str, Any]):
        """Generate anomaly detection insights"""
        for metric_name, metric_data in metrics_data.items():
            if metric_name not in self.metrics:
                continue
            
            current_value = metric_data.get("current_value", 0)
            is_anomaly, z_score, details = self.anomaly_detector.detect_anomaly(metric_name, current_value)
            
            if is_anomaly:
                insight = Insight(
                    id=f"anomaly_{metric_name}_{int(datetime.now().timestamp())}",
                    insight_type=InsightType.ANOMALY,
                    title=f"Anomaly Detected in {metric_name}",
                    description=f"Unusual value detected: {current_value:.2f} (Z-score: {z_score:.2f})",
                    confidence=min(z_score / 3.0, 1.0),  # Normalize to 0-1
                    impact="high" if z_score > 3 else "medium",
                    metrics_involved=[metric_name],
                    details=details,
                    recommendations=[
                        "Investigate recent changes to the system",
                        "Check for potential sensor malfunctions",
                        "Review system logs for related events"
                    ],
                    generated_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=1)
                )
                
                self.insights.append(insight)
    
    async def _generate_trend_insights(self, metrics_data: Dict[str, Any]):
        """Generate trend analysis insights"""
        for metric_name in metrics_data:
            if metric_name not in self.metrics:
                continue
            
            trend_analysis = self.trend_analyzer.analyze_trend(metric_name, hours=24)
            
            if trend_analysis["confidence"] > 0.7 and trend_analysis["trend"] != "stable":
                insight = Insight(
                    id=f"trend_{metric_name}_{int(datetime.now().timestamp())}",
                    insight_type=InsightType.TREND,
                    title=f"Trend Detected in {metric_name}",
                    description=f"{trend_analysis['trend'].title()} trend with {trend_analysis['confidence']:.1%} confidence",
                    confidence=trend_analysis["confidence"],
                    impact="medium",
                    metrics_involved=[metric_name],
                    details=trend_analysis,
                    recommendations=self._generate_trend_recommendations(metric_name, trend_analysis),
                    generated_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=6)
                )
                
                self.insights.append(insight)
    
    async def _generate_correlation_insights(self, metrics_data: Dict[str, Any]):
        """Generate correlation insights"""
        for metric_name in metrics_data:
            if metric_name not in self.metrics:
                continue
            
            correlations = self.correlation_analyzer.find_correlations(metric_name, hours=24)
            
            # Only add top correlation as insight
            if correlations and correlations[0]["strength"] == "strong":
                correlation = correlations[0]
                
                insight = Insight(
                    id=f"correlation_{metric_name}_{int(datetime.now().timestamp())}",
                    insight_type=InsightType.CORRELATION,
                    title=f"Strong Correlation: {metric_name} & {correlation['metric']}",
                    description=f"{correlation['direction'].title()} correlation ({correlation['correlation']:.3f})",
                    confidence=abs(correlation["correlation"]),
                    impact="medium",
                    metrics_involved=[metric_name, correlation["metric"]],
                    details=correlation,
                    recommendations=[
                        f"Investigate relationship between {metric_name} and {correlation['metric']}",
                        "Consider if changes in one metric affect the other",
                        "Use this correlation for predictive modeling"
                    ],
                    generated_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=12)
                )
                
                self.insights.append(insight)
    
    async def _generate_optimization_insights(self, metrics_data: Dict[str, Any]):
        """Generate performance optimization insights"""
        recommendations = self.performance_optimizer.generate_recommendations(metrics_data)
        
        for rec in recommendations[:3]:  # Top 3 recommendations
            insight = Insight(
                id=f"optimization_{rec['rule']}_{int(datetime.now().timestamp())}",
                insight_type=InsightType.OPTIMIZATION,
                title=f"Optimization Opportunity: {rec['category'].title()}",
                description=rec["recommendation"],
                confidence=0.8,
                impact=rec["impact"],
                metrics_involved=[rec["metric"]],
                details=rec,
                recommendations=[rec["recommendation"]],
                generated_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=24)
            )
            
            self.insights.append(insight)
    
    def _generate_trend_recommendations(self, metric_name: str, trend_analysis: Dict) -> List[str]:
        """Generate recommendations based on trend"""
        trend = trend_analysis["trend"]
        recommendations = []
        
        if trend == "increasing":
            if "temp" in metric_name:
                recommendations.append("Monitor cooling system performance")
                recommendations.append("Check for potential overheating issues")
            elif "power" in metric_name:
                recommendations.append("Review power management settings")
                recommendations.append("Consider workload optimization")
        elif trend == "decreasing":
            if "health" in metric_name:
                recommendations.append("Investigate potential hardware degradation")
                recommendations.append("Schedule preventive maintenance")
            elif "efficiency" in metric_name:
                recommendations.append("Review recent configuration changes")
                recommendations.append("Check for performance bottlenecks")
        
        return recommendations
    
    def _cleanup_old_insights(self):
        """Remove expired insights"""
        now = datetime.now()
        while self.insights and self.insights[0].expires_at and self.insights[0].expires_at < now:
            self.insights.popleft()
    
    def get_insights(self, insight_type: Optional[InsightType] = None, 
                    limit: int = 50) -> List[Insight]:
        """Get insights, optionally filtered by type"""
        insights = list(self.insights)
        
        if insight_type:
            insights = [i for i in insights if i.insight_type == insight_type]
        
        # Sort by generated time (newest first) and limit
        insights.sort(key=lambda x: x.generated_at, reverse=True)
        
        return insights[:limit]
    
    def get_analytics_summary(self) -> Dict[str, Any]:
        """Get comprehensive analytics summary"""
        # Insight statistics
        insights_by_type = defaultdict(int)
        insights_by_impact = defaultdict(int)
        
        for insight in self.insights:
            insights_by_type[insight.insight_type.value] += 1
            insights_by_impact[insight.impact] += 1
        
        # Metric statistics
        total_metrics = len(self.metrics)
        
        # Recent trends
        recent_trends = {}
        for metric_name in self.metrics:
            trend_analysis = self.trend_analyzer.analyze_trend(metric_name, hours=6)
            if trend_analysis["confidence"] > 0.5:
                recent_trends[metric_name] = trend_analysis
        
        # Performance score
        performance_score = self._calculate_performance_score()
        
        return {
            "timestamp": datetime.now().isoformat(),
            "insights": {
                "total": len(self.insights),
                "by_type": dict(insights_by_type),
                "by_impact": dict(insights_by_impact),
                "recent": len([i for i in self.insights if i.generated_at > datetime.now() - timedelta(hours=1)])
            },
            "metrics": {
                "total": total_metrics,
                "monitored": total_metrics
            },
            "trends": {
                "total": len(recent_trends),
                "increasing": len([t for t in recent_trends.values() if t["trend"] == "increasing"]),
                "decreasing": len([t for t in recent_trends.values() if t["trend"] == "decreasing"]),
                "stable": len([t for t in recent_trends.values() if t["trend"] == "stable"])
            },
            "performance": {
                "score": performance_score,
                "grade": self._get_performance_grade(performance_score)
            },
            "recommendations": len(self.get_insights(InsightType.OPTIMIZATION))
        }
    
    def _calculate_performance_score(self) -> float:
        """Calculate overall performance score (0-100)"""
        if not self.insights:
            return 85.0  # Default good score
        
        # Score based on insights
        total_insights = len(self.insights)
        critical_insights = len([i for i in self.insights if i.impact == "critical"])
        high_insights = len([i for i in self.insights if i.impact == "high"])
        
        # Start with 100 and deduct points for issues
        score = 100.0
        score -= (critical_insights * 15)  # -15 points per critical issue
        score -= (high_insights * 8)      # -8 points per high issue
        score -= (total_insights * 0.5)   # -0.5 points per insight
        
        return max(0.0, min(100.0, score))
    
    def _get_performance_grade(self, score: float) -> str:
        """Get performance grade from score"""
        if score >= 90:
            return "A"
        elif score >= 80:
            return "B"
        elif score >= 70:
            return "C"
        elif score >= 60:
            return "D"
        else:
            return "F"

# Global analytics dashboard instance
analytics_dashboard = AnalyticsDashboard()
