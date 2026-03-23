"""
Predictive Analytics Engine for Dell Server AI Agent
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np
from collections import defaultdict, deque
import statistics
from dataclasses import dataclass

from models.server_models import (
    LogEntry, HealthStatus, PerformanceMetrics, ServerStatus, 
    ComponentType, Severity
)

logger = logging.getLogger(__name__)

@dataclass
class PredictionResult:
    """Prediction result with confidence and recommendations"""
    prediction_type: str
    confidence: float
    risk_level: str  # low, medium, high, critical
    timeframe: str  # hours, days, weeks
    description: str
    recommendations: List[str]
    affected_components: List[str]
    data_points: int

class PredictiveAnalytics:
    """AI-powered predictive analytics for Dell servers"""
    
    def __init__(self, config):
        self.config = config
        self.historical_data = defaultdict(lambda: deque(maxlen=1000))
        self.prediction_models = {}
        self.anomaly_thresholds = {
            'temperature': 85.0,  # Celsius
            'power_consumption': 1000.0,  # Watts
            'fan_speed': 20000,  # RPM
            'memory_usage': 90.0,  # Percentage
            'cpu_usage': 95.0,  # Percentage
            'error_rate': 0.05  # 5% error rate threshold
        }
        
    def add_performance_data(self, server_id: str, metrics: PerformanceMetrics):
        """Add performance metrics to historical data"""
        timestamp = datetime.now()
        data_point = {
            'timestamp': timestamp,
            'cpu_utilization': metrics.cpu_utilization,
            'memory_utilization': metrics.memory_utilization,
            'disk_utilization': metrics.disk_utilization,
            'network_throughput': metrics.network_throughput,
            'power_consumption': metrics.power_consumption,
            'temperature_average': metrics.temperature_average
        }
        self.historical_data[server_id].append(data_point)
    
    def add_log_data(self, server_id: str, logs: List[LogEntry]):
        """Add log data for analysis"""
        current_time = datetime.now()
        recent_logs = [log for log in logs if current_time - log.timestamp <= timedelta(hours=24)]
        
        # Count errors by severity
        error_counts = defaultdict(int)
        for log in recent_logs:
            error_counts[log.severity.value] += 1
        
        # Store error rate
        total_logs = len(recent_logs)
        if total_logs > 0:
            error_rate = (error_counts.get('error', 0) + error_counts.get('critical', 0)) / total_logs
            self.historical_data[f"{server_id}_error_rate"].append({
                'timestamp': current_time,
                'error_rate': error_rate,
                'total_errors': error_counts.get('error', 0) + error_counts.get('critical', 0)
            })
    
    def predict_hardware_failure(self, server_id: str) -> List[PredictionResult]:
        """Predict potential hardware failures"""
        predictions = []
        
        if server_id not in self.historical_data:
            return predictions
        
        data_points = list(self.historical_data[server_id])
        if len(data_points) < 10:  # Need sufficient data for prediction
            return predictions
        
        # Temperature-based predictions
        temp_predictions = self._predict_temperature_failures(server_id, data_points)
        predictions.extend(temp_predictions)
        
        # Power consumption predictions
        power_predictions = self._predict_power_issues(server_id, data_points)
        predictions.extend(power_predictions)
        
        # Performance degradation predictions
        perf_predictions = self._predict_performance_degradation(server_id, data_points)
        predictions.extend(perf_predictions)
        
        # Error rate predictions
        error_predictions = self._predict_error_trends(server_id)
        predictions.extend(error_predictions)
        
        return predictions
    
    def _predict_temperature_failures(self, server_id: str, data_points: List[Dict]) -> List[PredictionResult]:
        """Predict temperature-related failures"""
        predictions = []
        
        temperatures = [dp['temperature_average'] for dp in data_points if dp['temperature_average']]
        if len(temperatures) < 5:
            return predictions
        
        # Calculate trend
        recent_temps = temperatures[-10:]
        avg_temp = statistics.mean(recent_temps)
        max_temp = max(recent_temps)
        
        # Check for increasing trend
        if len(recent_temps) >= 5:
            trend_slope = self._calculate_trend(recent_temps)
            
            if trend_slope > 0.5 and avg_temp > 70:  # Increasing trend and high average
                predictions.append(PredictionResult(
                    prediction_type="temperature_failure",
                    confidence=min(0.9, 0.5 + (trend_slope * 0.1)),
                    risk_level="high" if max_temp > 80 else "medium",
                    timeframe="days",
                    description=f"Temperature trend indicates potential overheating risk. Current average: {avg_temp:.1f}°C",
                    recommendations=[
                        "Check cooling system and fans",
                        "Verify airflow and ventilation",
                        "Clean dust from server components",
                        "Consider ambient temperature reduction"
                    ],
                    affected_components=["CPU", "System Board", "Power Supplies"],
                    data_points=len(temperatures)
                ))
        
        # Check for critical temperatures
        if max_temp > self.anomaly_thresholds['temperature']:
            predictions.append(PredictionResult(
                prediction_type="critical_temperature",
                confidence=0.95,
                risk_level="critical",
                timeframe="hours",
                description=f"Critical temperature detected: {max_temp:.1f}°C",
                recommendations=[
                    "Immediate cooling system inspection",
                    "Check for blocked air vents",
                    "Verify fan operation",
                    "Consider emergency shutdown if temperature persists"
                ],
                affected_components=["CPU", "System Board"],
                data_points=len(temperatures)
            ))
        
        return predictions
    
    def _predict_power_issues(self, server_id: str, data_points: List[Dict]) -> List[PredictionResult]:
        """Predict power-related issues"""
        predictions = []
        
        power_readings = [dp['power_consumption'] for dp in data_points if dp['power_consumption']]
        if len(power_readings) < 5:
            return predictions
        
        avg_power = statistics.mean(power_readings[-10:])
        max_power = max(power_readings[-10:])
        
        # Check for unusual power consumption
        if avg_power > self.anomaly_thresholds['power_consumption']:
            predictions.append(PredictionResult(
                prediction_type="power_overconsumption",
                confidence=0.8,
                risk_level="medium",
                timeframe="days",
                description=f"High power consumption detected: {avg_power:.1f}W",
                recommendations=[
                    "Check for failing power supplies",
                    "Verify power supply efficiency",
                    "Review server workload distribution",
                    "Consider power supply replacement"
                ],
                affected_components=["Power Supplies"],
                data_points=len(power_readings)
            ))
        
        # Check for power fluctuations
        if len(power_readings) >= 10:
            power_variance = statistics.variance(power_readings[-10:])
            if power_variance > 10000:  # High variance indicates fluctuations
                predictions.append(PredictionResult(
                    prediction_type="power_fluctuation",
                    confidence=0.7,
                    risk_level="medium",
                    timeframe="hours",
                    description="Power consumption fluctuations detected",
                    recommendations=[
                        "Check power supply stability",
                        "Verify UPS functionality",
                        "Monitor power quality",
                        "Check for failing components"
                    ],
                    affected_components=["Power Supplies", "UPS"],
                    data_points=len(power_readings)
                ))
        
        return predictions
    
    def _predict_performance_degradation(self, server_id: str, data_points: List[Dict]) -> List[PredictionResult]:
        """Predict performance degradation"""
        predictions = []
        
        cpu_readings = [dp['cpu_utilization'] for dp in data_points if dp['cpu_utilization']]
        memory_readings = [dp['memory_utilization'] for dp in data_points if dp['memory_utilization']]
        
        # CPU performance prediction
        if len(cpu_readings) >= 10:
            recent_cpu = cpu_readings[-10:]
            avg_cpu = statistics.mean(recent_cpu)
            cpu_trend = self._calculate_trend(recent_cpu)
            
            if avg_cpu > 80 and cpu_trend > 0.3:
                predictions.append(PredictionResult(
                    prediction_type="cpu_degradation",
                    confidence=min(0.85, 0.6 + (cpu_trend * 0.1)),
                    risk_level="high" if avg_cpu > 90 else "medium",
                    timeframe="days",
                    description=f"CPU utilization trending upward: {avg_cpu:.1f}% average",
                    recommendations=[
                        "Analyze CPU-intensive processes",
                        "Consider workload optimization",
                        "Check for memory bottlenecks",
                        "Plan for capacity upgrade"
                    ],
                    affected_components=["CPU", "Memory"],
                    data_points=len(cpu_readings)
                ))
        
        # Memory performance prediction
        if len(memory_readings) >= 10:
            recent_memory = memory_readings[-10:]
            avg_memory = statistics.mean(recent_memory)
            memory_trend = self._calculate_trend(recent_memory)
            
            if avg_memory > 85 and memory_trend > 0.2:
                predictions.append(PredictionResult(
                    prediction_type="memory_degradation",
                    confidence=min(0.8, 0.5 + (memory_trend * 0.1)),
                    risk_level="high" if avg_memory > 90 else "medium",
                    timeframe="days",
                    description=f"Memory utilization trending upward: {avg_memory:.1f}% average",
                    recommendations=[
                        "Check for memory leaks",
                        "Analyze memory usage patterns",
                        "Consider memory upgrade",
                        "Optimize application memory usage"
                    ],
                    affected_components=["Memory"],
                    data_points=len(memory_readings)
                ))
        
        return predictions
    
    def _predict_error_trends(self, server_id: str) -> List[PredictionResult]:
        """Predict error trends based on log analysis"""
        predictions = []
        
        error_key = f"{server_id}_error_rate"
        if error_key not in self.historical_data:
            return predictions
        
        error_data = list(self.historical_data[error_key])
        if len(error_data) < 5:
            return predictions
        
        recent_errors = error_data[-10:]
        error_rates = [ed['error_rate'] for ed in recent_errors]
        avg_error_rate = statistics.mean(error_rates)
        error_trend = self._calculate_trend(error_rates)
        
        # Predict increasing error rates
        if error_trend > 0.01 and avg_error_rate > 0.02:  # 2% error rate threshold
            predictions.append(PredictionResult(
                prediction_type="increasing_errors",
                confidence=min(0.9, 0.6 + (error_trend * 10)),
                risk_level="high" if avg_error_rate > 0.05 else "medium",
                timeframe="days",
                description=f"Error rate increasing: {avg_error_rate:.2%} average",
                recommendations=[
                    "Investigate root cause of errors",
                    "Check hardware component health",
                    "Review system logs for patterns",
                    "Schedule preventive maintenance"
                ],
                affected_components=["System", "Hardware"],
                data_points=len(error_rates)
            ))
        
        # Critical error rate prediction
        if avg_error_rate > self.anomaly_thresholds['error_rate']:
            predictions.append(PredictionResult(
                prediction_type="critical_error_rate",
                confidence=0.95,
                risk_level="critical",
                timeframe="hours",
                description=f"Critical error rate detected: {avg_error_rate:.2%}",
                recommendations=[
                    "Immediate system inspection required",
                    "Check for failing hardware components",
                    "Review recent system changes",
                    "Consider emergency maintenance"
                ],
                affected_components=["System", "Hardware"],
                data_points=len(error_rates)
            ))
        
        return predictions
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate linear trend slope for a series of values"""
        if len(values) < 2:
            return 0.0
        
        x = list(range(len(values)))
        y = values
        
        # Simple linear regression
        n = len(values)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        if n * sum_x2 - sum_x ** 2 == 0:
            return 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        return slope
    
    def predict_maintenance_needs(self, server_id: str) -> List[PredictionResult]:
        """Predict maintenance needs based on various factors"""
        predictions = []
        
        # Combine all predictions
        hardware_predictions = self.predict_hardware_failure(server_id)
        predictions.extend(hardware_predictions)
        
        # Add maintenance-specific predictions
        if server_id in self.historical_data:
            data_points = list(self.historical_data[server_id])
            if len(data_points) >= 20:  # Sufficient data for maintenance prediction
                # Predict general maintenance needs
                age_factor = self._calculate_system_age_factor(data_points)
                if age_factor > 0.7:
                    predictions.append(PredictionResult(
                        prediction_type="preventive_maintenance",
                        confidence=0.75,
                        risk_level="medium",
                        timeframe="weeks",
                        description="System shows signs of aging, preventive maintenance recommended",
                        recommendations=[
                            "Schedule comprehensive system inspection",
                            "Check all hardware components",
                            "Update firmware and drivers",
                            "Clean internal components"
                        ],
                        affected_components=["System"],
                        data_points=len(data_points)
                    ))
        
        return predictions
    
    def _calculate_system_age_factor(self, data_points: List[Dict]) -> float:
        """Calculate system age factor based on performance degradation"""
        if len(data_points) < 20:
            return 0.0
        
        # Compare oldest vs newest performance
        oldest_data = data_points[:5]
        newest_data = data_points[-5:]
        
        old_avg_cpu = statistics.mean([dp['cpu_utilization'] for dp in oldest_data if dp['cpu_utilization']] or [0])
        new_avg_cpu = statistics.mean([dp['cpu_utilization'] for dp in newest_data if dp['cpu_utilization']] or [0])
        
        old_avg_memory = statistics.mean([dp['memory_utilization'] for dp in oldest_data if dp['memory_utilization']] or [0])
        new_avg_memory = statistics.mean([dp['memory_utilization'] for dp in newest_data if dp['memory_utilization']] or [0])
        
        cpu_degradation = (new_avg_cpu - old_avg_cpu) / max(old_avg_cpu, 1)
        memory_degradation = (new_avg_memory - old_avg_memory) / max(old_avg_memory, 1)
        
        return max(0, min(1, (cpu_degradation + memory_degradation) / 2))
    
    def get_anomaly_detection(self, server_id: str) -> Dict[str, Any]:
        """Detect anomalies in current system behavior"""
        anomalies = {}
        
        if server_id not in self.historical_data:
            return anomalies
        
        data_points = list(self.historical_data[server_id])
        if len(data_points) < 5:
            return anomalies
        
        latest_data = data_points[-1]
        
        # Check each metric against thresholds
        for metric, threshold in self.anomaly_thresholds.items():
            value = getattr(latest_data, metric, None)
            if value is not None:
                if metric == 'temperature' and latest_data.get('temperature_average'):
                    temp = latest_data['temperature_average']
                    anomalies['temperature'] = {
                        'value': temp,
                        'threshold': threshold,
                        'status': 'critical' if temp > threshold else 'normal',
                        'deviation': temp - threshold if temp > threshold else 0
                    }
                
                elif metric == 'power_consumption' and latest_data.get('power_consumption'):
                    power = latest_data['power_consumption']
                    anomalies['power_consumption'] = {
                        'value': power,
                        'threshold': threshold,
                        'status': 'warning' if power > threshold * 0.8 else 'normal',
                        'deviation': power - threshold if power > threshold else 0
                    }
        
        return anomalies
    
    def generate_health_score(self, server_id: str) -> Dict[str, Any]:
        """Generate overall health score for the server"""
        if server_id not in self.historical_data:
            return {'score': 0, 'status': 'unknown', 'factors': []}
        
        data_points = list(self.historical_data[server_id])
        if len(data_points) < 5:
            return {'score': 0, 'status': 'insufficient_data', 'factors': []}
        
        latest_data = data_points[-1]
        factors = []
        total_score = 100
        
        # Temperature factor
        if latest_data.get('temperature_average'):
            temp = latest_data['temperature_average']
            if temp > 85:
                temp_score = max(0, 100 - (temp - 85) * 5)
                factors.append({'name': 'temperature', 'score': temp_score, 'weight': 0.2})
                total_score -= (100 - temp_score) * 0.2
        
        # CPU utilization factor
        if latest_data.get('cpu_utilization'):
            cpu = latest_data['cpu_utilization']
            if cpu > 80:
                cpu_score = max(0, 100 - (cpu - 80) * 2)
                factors.append({'name': 'cpu_utilization', 'score': cpu_score, 'weight': 0.25})
                total_score -= (100 - cpu_score) * 0.25
        
        # Memory utilization factor
        if latest_data.get('memory_utilization'):
            memory = latest_data['memory_utilization']
            if memory > 85:
                memory_score = max(0, 100 - (memory - 85) * 2)
                factors.append({'name': 'memory_utilization', 'score': memory_score, 'weight': 0.25})
                total_score -= (100 - memory_score) * 0.25
        
        # Error rate factor
        error_key = f"{server_id}_error_rate"
        if error_key in self.historical_data:
            error_data = list(self.historical_data[error_key])
            if error_data:
                latest_error_rate = error_data[-1]['error_rate']
                if latest_error_rate > 0.01:  # 1% error rate
                    error_score = max(0, 100 - latest_error_rate * 1000)
                    factors.append({'name': 'error_rate', 'score': error_score, 'weight': 0.3})
                    total_score -= (100 - error_score) * 0.3
        
        # Determine status
        if total_score >= 90:
            status = 'excellent'
        elif total_score >= 75:
            status = 'good'
        elif total_score >= 60:
            status = 'fair'
        elif total_score >= 40:
            status = 'poor'
        else:
            status = 'critical'
        
        return {
            'score': round(total_score, 1),
            'status': status,
            'factors': factors,
            'data_points': len(data_points)
        }
