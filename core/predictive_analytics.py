"""
Predictive analytics engine for Dell PowerEdge servers.
Analyzes historical data to predict potential failures and recommend preventive actions.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import statistics
import math

logger = logging.getLogger(__name__)

class FailureRiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class TrendData:
    """Historical data points for trend analysis"""
    timestamps: List[datetime]
    values: List[float]
    unit: str
    
    def __post_init__(self):
        if len(self.timestamps) != len(self.values):
            raise ValueError("Timestamps and values must have same length")

@dataclass
class PredictionResult:
    """Result of predictive analysis"""
    component: str
    risk_level: FailureRiskLevel
    confidence: float  # 0-1
    predicted_failure_date: Optional[datetime]
    trend_direction: str  # "increasing", "decreasing", "stable"
    trend_slope: float
    recommendation: str
    supporting_data: Dict[str, Any]

class PredictiveAnalytics:
    """Predictive analytics engine for server health monitoring"""
    
    def __init__(self):
        # Risk thresholds for different metrics
        self.risk_thresholds = {
            "temperature": {
                "degradation_rate": 2.0,  # °C per month
                "absolute_warning": 75.0,
                "absolute_critical": 85.0
            },
            "power_efficiency": {
                "degradation_rate": 0.02,  # 2% per month
                "absolute_warning": 0.80,
                "absolute_critical": 0.70
            },
            "memory_errors": {
                "error_rate_growth": 1.5,  # 1.5x per month
                "absolute_warning": 10,    # errors per day
                "absolute_critical": 50
            },
            "storage_health": {
                "degradation_rate": 0.05,  # 5% per month
                "absolute_warning": 0.90,
                "absolute_critical": 0.80
            },
            "fan_speed_variance": {
                "variance_threshold": 0.3,  # 30% variance indicates bearing wear
                "noise_increase_rate": 100  # RPM increase per month
            }
        }
        
        # Component failure rates (based on industry data)
        self.component_failure_rates = {
            "PSU": 0.03,      # 3% annual failure rate
            "DIMM": 0.02,     # 2% annual failure rate
            "Drive": 0.05,    # 5% annual failure rate
            "Fan": 0.04,      # 4% annual failure rate
            "CPU": 0.01,      # 1% annual failure rate
            "NIC": 0.02       # 2% annual failure rate
        }
    
    def analyze_temperature_trend(self, trend_data: TrendData, current_temp: float) -> PredictionResult:
        """Analyze temperature trends and predict overheating risk"""
        if len(trend_data.values) < 5:
            return PredictionResult(
                component="thermal",
                risk_level=FailureRiskLevel.LOW,
                confidence=0.0,
                predicted_failure_date=None,
                trend_direction="insufficient_data",
                trend_slope=0.0,
                recommendation="Insufficient data for prediction. Continue monitoring.",
                supporting_data={"data_points": len(trend_data.values)}
            )
        
        # Calculate linear trend
        timestamps_unix = [t.timestamp() for t in trend_data.timestamps]
        slope, intercept = self._linear_regression(timestamps_unix, trend_data.values)
        
        # Convert slope from per-second to per-month
        slope_per_month = slope * (30 * 24 * 3600)
        
        # Determine trend direction
        if abs(slope_per_month) < 0.1:
            trend_direction = "stable"
        elif slope_per_month > 0:
            trend_direction = "increasing"
        else:
            trend_direction = "decreasing"
        
        # Calculate risk
        risk_level = FailureRiskLevel.LOW
        confidence = min(abs(slope_per_month) / self.risk_thresholds["temperature"]["degradation_rate"], 1.0)
        
        predicted_failure_date = None
        recommendation = "Temperature trend is normal."
        
        if trend_direction == "increasing" and slope_per_month > 0.5:
            # Predict when temperature will reach critical threshold
            critical_threshold = self.risk_thresholds["temperature"]["absolute_critical"]
            if current_temp < critical_threshold:
                months_to_critical = (critical_threshold - current_temp) / slope_per_month
                if months_to_critical > 0 and months_to_critical < 12:
                    predicted_failure_date = datetime.utcnow() + timedelta(days=months_to_critical * 30)
                    risk_level = FailureRiskLevel.HIGH if months_to_critical < 3 else FailureRiskLevel.MEDIUM
                    recommendation = f"Temperature increasing at {slope_per_month:.1f}°C/month. Predicted critical in {months_to_critical:.1f} months. Check cooling system."
        
        elif current_temp >= self.risk_thresholds["temperature"]["absolute_critical"]:
            risk_level = FailureRiskLevel.CRITICAL
            recommendation = "Temperature at critical level. Immediate action required."
        elif current_temp >= self.risk_thresholds["temperature"]["absolute_warning"]:
            risk_level = FailureRiskLevel.MEDIUM
            recommendation = "Temperature elevated. Monitor closely and check airflow."
        
        return PredictionResult(
            component="thermal",
            risk_level=risk_level,
            confidence=confidence,
            predicted_failure_date=predicted_failure_date,
            trend_direction=trend_direction,
            trend_slope=slope_per_month,
            recommendation=recommendation,
            supporting_data={
                "current_temp": current_temp,
                "trend_slope_c_per_month": slope_per_month,
                "data_points": len(trend_data.values)
            }
        )
    
    def analyze_power_efficiency_trend(self, trend_data: TrendData, current_efficiency: float) -> PredictionResult:
        """Analyze power supply efficiency trends"""
        if len(trend_data.values) < 5:
            return PredictionResult(
                component="power",
                risk_level=FailureRiskLevel.LOW,
                confidence=0.0,
                predicted_failure_date=None,
                trend_direction="insufficient_data",
                trend_slope=0.0,
                recommendation="Insufficient data for prediction.",
                supporting_data={"data_points": len(trend_data.values)}
            )
        
        timestamps_unix = [t.timestamp() for t in trend_data.timestamps]
        slope, intercept = self._linear_regression(timestamps_unix, trend_data.values)
        
        # Convert to per-month change
        slope_per_month = slope * (30 * 24 * 3600)
        
        trend_direction = "stable" if abs(slope_per_month) < 0.001 else ("decreasing" if slope_per_month < 0 else "increasing")
        
        risk_level = FailureRiskLevel.LOW
        confidence = min(abs(slope_per_month) / self.risk_thresholds["power_efficiency"]["degradation_rate"], 1.0)
        
        predicted_failure_date = None
        recommendation = "Power efficiency is normal."
        
        if trend_direction == "decreasing":
            # Predict when efficiency will drop to critical level
            critical_threshold = self.risk_thresholds["power_efficiency"]["absolute_critical"]
            if current_efficiency > critical_threshold:
                months_to_critical = (current_efficiency - critical_threshold) / abs(slope_per_month)
                if months_to_critical > 0 and months_to_critical < 12:
                    predicted_failure_date = datetime.utcnow() + timedelta(days=months_to_critical * 30)
                    risk_level = FailureRiskLevel.HIGH if months_to_critical < 3 else FailureRiskLevel.MEDIUM
                    recommendation = f"Efficiency declining at {abs(slope_per_month)*100:.1f}%/month. Predicted critical in {months_to_critical:.1f} months. Plan PSU replacement."
        
        elif current_efficiency <= self.risk_thresholds["power_efficiency"]["absolute_critical"]:
            risk_level = FailureRiskLevel.CRITICAL
            recommendation = "Power supply efficiency critical. Replace immediately."
        elif current_efficiency <= self.risk_thresholds["power_efficiency"]["absolute_warning"]:
            risk_level = FailureRiskLevel.MEDIUM
            recommendation = "Power supply efficiency degraded. Monitor and plan replacement."
        
        return PredictionResult(
            component="power",
            risk_level=risk_level,
            confidence=confidence,
            predicted_failure_date=predicted_failure_date,
            trend_direction=trend_direction,
            trend_slope=slope_per_month,
            recommendation=recommendation,
            supporting_data={
                "current_efficiency": current_efficiency,
                "trend_slope_per_month": slope_per_month,
                "data_points": len(trend_data.values)
            }
        )
    
    def analyze_memory_error_trend(self, error_counts: List[int], time_window_days: int = 30) -> PredictionResult:
        """Analyze memory error patterns"""
        if not error_counts:
            return PredictionResult(
                component="memory",
                risk_level=FailureRiskLevel.LOW,
                confidence=0.0,
                predicted_failure_date=None,
                trend_direction="no_errors",
                trend_slope=0.0,
                recommendation="No memory errors detected.",
                supporting_data={"total_errors": 0}
            )
        
        total_errors = sum(error_counts)
        avg_errors_per_day = total_errors / max(len(error_counts), 1)
        
        # Calculate trend in error rate
        if len(error_counts) >= 7:
            recent_avg = statistics.mean(error_counts[-7:])
            older_avg = statistics.mean(error_counts[:-7]) if len(error_counts) > 7 else avg_errors_per_day
            trend_slope = (recent_avg - older_avg) / max(older_avg, 1)
        else:
            trend_slope = 0
        
        trend_direction = "stable" if abs(trend_slope) < 0.1 else ("increasing" if trend_slope > 0 else "decreasing")
        
        risk_level = FailureRiskLevel.LOW
        confidence = min(avg_errors_per_day / self.risk_thresholds["memory_errors"]["absolute_warning"], 1.0)
        
        predicted_failure_date = None
        recommendation = "Memory error rate is normal."
        
        if avg_errors_per_day >= self.risk_thresholds["memory_errors"]["absolute_critical"]:
            risk_level = FailureRiskLevel.CRITICAL
            recommendation = "Critical memory error rate. Immediate DIMM replacement required."
        elif avg_errors_per_day >= self.risk_thresholds["memory_errors"]["absolute_warning"]:
            risk_level = FailureRiskLevel.MEDIUM
            recommendation = "Elevated memory error rate. Monitor closely and plan replacement."
        
        if trend_direction == "increasing" and trend_slope > 0.2:
            risk_level = FailureRiskLevel.HIGH if risk_level != FailureRiskLevel.CRITICAL else FailureRiskLevel.CRITICAL
            recommendation += " Error rate increasing significantly. Accelerate replacement plans."
        
        return PredictionResult(
            component="memory",
            risk_level=risk_level,
            confidence=confidence,
            predicted_failure_date=predicted_failure_date,
            trend_direction=trend_direction,
            trend_slope=trend_slope,
            recommendation=recommendation,
            supporting_data={
                "total_errors": total_errors,
                "avg_errors_per_day": avg_errors_per_day,
                "trend_slope": trend_slope
            }
        )
    
    def calculate_component_failure_probability(self, component_type: str, age_months: int, 
                                            health_score: float, operating_hours: int) -> Dict[str, Any]:
        """Calculate probability of component failure based on multiple factors"""
        base_annual_rate = self.component_failure_rates.get(component_type, 0.02)
        
        # Age factor (bathtub curve)
        if age_months < 6:
            age_factor = 2.0  # Infant mortality
        elif age_months < 36:
            age_factor = 0.5  # Normal operation
        elif age_months < 72:
            age_factor = 1.0  # Aging begins
        else:
            age_factor = 2.0 + (age_months - 72) / 12  # Wear-out period
        
        # Health score factor
        health_factor = max(0.1, (100 - health_score) / 50)
        
        # Operating hours factor
        hours_factor = min(2.0, operating_hours / (365 * 24))  # Normalized to 1 year
        
        # Combined failure rate
        annual_failure_rate = base_annual_rate * age_factor * health_factor * hours_factor
        
        # Monthly and daily probabilities
        monthly_failure_prob = 1 - math.exp(-annual_failure_rate / 12)
        daily_failure_prob = 1 - math.exp(-annual_failure_rate / 365)
        
        return {
            "component_type": component_type,
            "annual_failure_rate": annual_failure_rate,
            "monthly_failure_probability": monthly_failure_prob,
            "daily_failure_probability": daily_failure_prob,
            "risk_factors": {
                "age_factor": age_factor,
                "health_factor": health_factor,
                "hours_factor": hours_factor
            },
            "recommendation": self._get_maintenance_recommendation(component_type, annual_failure_rate)
        }
    
    def _get_maintenance_recommendation(self, component_type: str, annual_failure_rate: float) -> str:
        """Get maintenance recommendation based on failure rate"""
        if annual_failure_rate > 0.1:  # >10% annual
            return f"High failure risk for {component_type}. Schedule immediate replacement."
        elif annual_failure_rate > 0.05:  # >5% annual
            return f"Elevated failure risk for {component_type}. Plan replacement within 3 months."
        elif annual_failure_rate > 0.02:  # >2% annual
            return f"Moderate failure risk for {component_type}. Monitor and plan replacement within 6 months."
        else:
            return f"Low failure risk for {component_type}. Continue normal monitoring."
    
    def _linear_regression(self, x: List[float], y: List[float]) -> Tuple[float, float]:
        """Calculate linear regression slope and intercept"""
        n = len(x)
        if n < 2:
            return 0.0, 0.0
        
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(xi * yi for xi, yi in zip(x, y))
        sum_x2 = sum(xi * xi for xi in x)
        
        denominator = n * sum_x2 - sum_x * sum_x
        if denominator == 0:
            return 0.0, 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        intercept = (sum_y - slope * sum_x) / n
        
        return slope, intercept
    
    async def generate_predictive_report(self, server_data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate comprehensive predictive analytics report"""
        predictions = []
        
        # Analyze temperature trends
        if "temperature_history" in server_data:
            temp_data = server_data["temperature_history"]
            if temp_data and len(temp_data) >= 5:
                trend = TrendData(
                    timestamps=[datetime.fromisoformat(d["timestamp"]) for d in temp_data],
                    values=[d["value"] for d in temp_data],
                    unit="°C"
                )
                current_temp = temp_data[-1]["value"]
                prediction = self.analyze_temperature_trend(trend, current_temp)
                predictions.append(prediction)
        
        # Analyze power efficiency
        if "power_history" in server_data:
            power_data = server_data["power_history"]
            if power_data and len(power_data) >= 5:
                trend = TrendData(
                    timestamps=[datetime.fromisoformat(d["timestamp"]) for d in power_data],
                    values=[d["efficiency"] for d in power_data],
                    unit="%"
                )
                current_efficiency = power_data[-1]["efficiency"]
                prediction = self.analyze_power_efficiency_trend(trend, current_efficiency)
                predictions.append(prediction)
        
        # Analyze memory errors
        if "memory_errors" in server_data:
            error_counts = server_data["memory_errors"]
            prediction = self.analyze_memory_error_trend(error_counts)
            predictions.append(prediction)
        
        # Calculate component failure probabilities
        component_risks = []
        for component in server_data.get("components", []):
            risk = self.calculate_component_failure_probability(
                component["type"],
                component.get("age_months", 0),
                component.get("health_score", 100),
                component.get("operating_hours", 0)
            )
            component_risks.append(risk)
        
        # Overall risk assessment
        high_risk_components = [p for p in predictions if p.risk_level in [FailureRiskLevel.HIGH, FailureRiskLevel.CRITICAL]]
        overall_risk = FailureRiskLevel.CRITICAL if high_risk_components else FailureRiskLevel.HIGH if any(p.risk_level == FailureRiskLevel.MEDIUM for p in predictions) else FailureRiskLevel.LOW
        
        return {
            "overall_risk_level": overall_risk.value,
            "predictions": [
                {
                    "component": p.component,
                    "risk_level": p.risk_level.value,
                    "confidence": p.confidence,
                    "predicted_failure_date": p.predicted_failure_date.isoformat() if p.predicted_failure_date else None,
                    "trend_direction": p.trend_direction,
                    "recommendation": p.recommendation
                }
                for p in predictions
            ],
            "component_risks": component_risks,
            "summary": {
                "total_predictions": len(predictions),
                "high_risk_count": len(high_risk_components),
                "recommendations": [p.recommendation for p in predictions if p.risk_level in [FailureRiskLevel.HIGH, FailureRiskLevel.CRITICAL]]
            }
        }

# Global predictive analytics instance
predictive_analytics = PredictiveAnalytics()
