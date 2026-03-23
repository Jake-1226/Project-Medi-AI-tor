"""
Real-time Performance Monitoring System
Provides WebSocket-based streaming of server metrics with historical data storage
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
import time
from collections import deque
import statistics

logger = logging.getLogger(__name__)

@dataclass
class MetricPoint:
    """Single metric data point"""
    timestamp: datetime
    value: float
    unit: str
    status: str  # "normal", "warning", "critical"
    
    def to_dict(self) -> Dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "value": self.value,
            "unit": self.unit,
            "status": self.status
        }

@dataclass
class MetricSeries:
    """Time series data for a specific metric"""
    name: str
    description: str
    unit: str
    current_value: float
    current_status: str
    threshold_warning: float
    threshold_critical: float
    history: deque  # Last 100 data points
    
    def __post_init__(self):
        if isinstance(self.history, list):
            self.history = deque(self.history, maxlen=100)
    
    def add_point(self, point: MetricPoint):
        """Add new data point"""
        self.current_value = point.value
        self.current_status = point.status
        self.history.append(point)
    
    def get_trend(self, minutes: int = 10) -> str:
        """Calculate trend over specified minutes"""
        if len(self.history) < 2:
            return "stable"
        
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_points = [p for p in self.history if p.timestamp >= cutoff_time]
        
        if len(recent_points) < 2:
            return "stable"
        
        values = [p.value for p in recent_points]
        if len(values) < 2:
            return "stable"
        
        # Simple linear regression for trend
        x = list(range(len(values)))
        n = len(values)
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] * x[i] for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x)
        
        if abs(slope) < 0.01:
            return "stable"
        elif slope > 0:
            return "increasing"
        else:
            return "decreasing"
    
    def get_average(self, minutes: int = 10) -> float:
        """Get average value over specified minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_points = [p for p in self.history if p.timestamp >= cutoff_time]
        
        if not recent_points:
            return self.current_value
        
        return statistics.mean(p.value for p in recent_points)
    
    def get_max(self, minutes: int = 10) -> float:
        """Get maximum value over specified minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_points = [p for p in self.history if p.timestamp >= cutoff_time]
        
        if not recent_points:
            return self.current_value
        
        return max(p.value for p in recent_points)
    
    def get_min(self, minutes: int = 10) -> float:
        """Get minimum value over specified minutes"""
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        recent_points = [p for p in self.history if p.timestamp >= cutoff_time]
        
        if not recent_points:
            return self.current_value
        
        return min(p.value for p in recent_points)

class RealtimeMonitor:
    """Real-time monitoring system for server metrics"""
    
    def __init__(self):
        self.metrics: Dict[str, MetricSeries] = {}
        self.websocket_connections: List[Any] = []
        self.monitoring_active = False
        self.monitoring_task: Optional[asyncio.Task] = None
        self.redfish_client = None
        
        # Initialize metric definitions
        self._initialize_metrics()
    
    def _initialize_metrics(self):
        """Initialize all metric series"""
        metric_configs = {
            # Temperature metrics
            "inlet_temp": {
                "name": "inlet_temp",
                "description": "Inlet Temperature",
                "unit": "°C",
                "threshold_warning": 30.0,
                "threshold_critical": 35.0
            },
            "cpu_temp": {
                "name": "cpu_temp", 
                "description": "CPU Temperature",
                "unit": "°C",
                "threshold_warning": 75.0,
                "threshold_critical": 85.0
            },
            "max_temp": {
                "name": "max_temp",
                "description": "Maximum Temperature",
                "unit": "°C", 
                "threshold_warning": 80.0,
                "threshold_critical": 90.0
            },
            
            # Fan metrics
            "avg_fan_speed": {
                "name": "avg_fan_speed",
                "description": "Average Fan Speed",
                "unit": "RPM",
                "threshold_warning": 8000,
                "threshold_critical": 10000
            },
            "max_fan_speed": {
                "name": "max_fan_speed",
                "description": "Maximum Fan Speed", 
                "unit": "RPM",
                "threshold_warning": 9000,
                "threshold_critical": 11000
            },
            
            # Power metrics
            "power_consumption": {
                "name": "power_consumption",
                "description": "Power Consumption",
                "unit": "W",
                "threshold_warning": 600,
                "threshold_critical": 750
            },
            "power_efficiency": {
                "name": "power_efficiency",
                "description": "Power Efficiency",
                "unit": "%",
                "threshold_warning": 80.0,
                "threshold_critical": 70.0
            },
            
            # Memory metrics
            "memory_health": {
                "name": "memory_health",
                "description": "Memory Health Score",
                "unit": "%",
                "threshold_warning": 80.0,
                "threshold_critical": 60.0
            },
            
            # Storage metrics
            "storage_health": {
                "name": "storage_health", 
                "description": "Storage Health Score",
                "unit": "%",
                "threshold_warning": 80.0,
                "threshold_critical": 60.0
            },
            
            # System metrics
            "overall_health": {
                "name": "overall_health",
                "description": "Overall Health Score",
                "unit": "%",
                "threshold_warning": 80.0,
                "threshold_critical": 60.0
            }
        }
        
        for key, config in metric_configs.items():
            self.metrics[key] = MetricSeries(
                name=config["name"],
                description=config["description"],
                unit=config["unit"],
                current_value=0.0,
                current_status="normal",
                threshold_warning=config["threshold_warning"],
                threshold_critical=config["threshold_critical"],
                history=deque(maxlen=100)
            )
    
    async def start_monitoring(self, redfish_client, interval: int = 30):
        """Start real-time monitoring"""
        self.redfish_client = redfish_client
        self.monitoring_active = True
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
        
        self.monitoring_task = asyncio.create_task(self._monitoring_loop(interval))
        logger.info(f"Started real-time monitoring with {interval}s interval")
    
    async def stop_monitoring(self):
        """Stop real-time monitoring"""
        self.monitoring_active = False
        
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Stopped real-time monitoring")
    
    async def _monitoring_loop(self, interval: int):
        """Main monitoring loop"""
        while self.monitoring_active:
            try:
                await self._collect_metrics()
                await self._broadcast_updates()
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(interval)
    
    async def _collect_metrics(self):
        """Collect metrics from server"""
        if not self.redfish_client:
            return
        
        try:
            # Collect thermal data
            thermal_data = await self.redfish_client.get_temperature_sensors()
            await self._process_thermal_data(thermal_data)
            
            # Collect power data
            power_data = await self.redfish_client.get_power_supplies()
            await self._process_power_data(power_data)
            
            # Collect memory data
            memory_data = await self.redfish_client.get_memory()
            await self._process_memory_data(memory_data)
            
            # Collect storage data
            storage_data = await self.redfish_client.get_storage_devices()
            await self._process_storage_data(storage_data)
            
            # Calculate overall health
            await self._calculate_overall_health()
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
    
    async def _process_thermal_data(self, thermal_data: Dict):
        """Process thermal sensor data"""
        temperatures = thermal_data.get("Temperatures", [])
        fans = thermal_data.get("Fans", [])
        
        if temperatures:
            # Find inlet temperature
            inlet_temps = [t["ReadingCelsius"] for t in temperatures if "Inlet" in t.get("Name", "")]
            if inlet_temps:
                await self._update_metric("inlet_temp", inlet_temps[0])
            
            # Find CPU temperatures
            cpu_temps = [t["ReadingCelsius"] for t in temperatures if "CPU" in t.get("Name", "")]
            if cpu_temps:
                avg_cpu_temp = statistics.mean(cpu_temps)
                await self._update_metric("cpu_temp", avg_cpu_temp)
            
            # Maximum temperature
            max_temp = max(t["ReadingCelsius"] for t in temperatures) if temperatures else 0
            await self._update_metric("max_temp", max_temp)
        
        if fans:
            # Average fan speed
            fan_speeds = [f["Reading"] for f in fans if f.get("Reading")]
            if fan_speeds:
                avg_speed = statistics.mean(fan_speeds)
                await self._update_metric("avg_fan_speed", avg_speed)
                
                max_speed = max(fan_speeds)
                await self._update_metric("max_fan_speed", max_speed)
    
    async def _process_power_data(self, power_data: Dict):
        """Process power supply data"""
        psus = power_data.get("PowerSupplies", [])
        power_control = power_data.get("PowerControl", [])
        
        if psus:
            # Calculate total power consumption
            total_output = sum(psu.get("OutputWatts", 0) for psu in psus)
            await self._update_metric("power_consumption", total_output)
            
            # Calculate average efficiency
            efficiencies = []
            for psu in psus:
                output = psu.get("OutputWatts", 0)
                capacity = psu.get("CapacityWatts", 1)
                if capacity > 0:
                    efficiency = (output / capacity) * 100
                    efficiencies.append(efficiency)
            
            if efficiencies:
                avg_efficiency = statistics.mean(efficiencies)
                await self._update_metric("power_efficiency", avg_efficiency)
    
    async def _process_memory_data(self, memory_data: Dict):
        """Process memory data"""
        dimms = memory_data.get("Memory", [])
        
        if dimms:
            # Calculate memory health score
            healthy_dimms = 0
            total_dimms = len(dimms)
            
            for dimm in dimms:
                status = dimm.get("Status", {}).get("Health", "OK")
                if status in ["OK", "Good"]:
                    healthy_dimms += 1
            
            health_score = (healthy_dimms / total_dimms) * 100 if total_dimms > 0 else 100
            await self._update_metric("memory_health", health_score)
    
    async def _process_storage_data(self, storage_data: Dict):
        """Process storage data"""
        drives = storage_data.get("drives", [])
        
        if drives:
            # Calculate storage health score
            healthy_drives = 0
            total_drives = len(drives)
            
            for drive in drives:
                status = drive.get("Status", {}).get("Health", "OK")
                failure_predicted = drive.get("FailurePredicted", False)
                
                if status in ["OK", "Good"] and not failure_predicted:
                    healthy_drives += 1
            
            health_score = (healthy_drives / total_drives) * 100 if total_drives > 0 else 100
            await self._update_metric("storage_health", health_score)
    
    async def _calculate_overall_health(self):
        """Calculate overall health score"""
        health_scores = []
        
        # Weight different subsystems
        weights = {
            "max_temp": 0.25,
            "memory_health": 0.20,
            "storage_health": 0.20,
            "power_efficiency": 0.15,
            "avg_fan_speed": 0.20
        }
        
        for metric_name, weight in weights.items():
            if metric_name in self.metrics:
                metric = self.metrics[metric_name]
                # Convert metric to 0-100 scale
                if metric_name == "max_temp":
                    # Lower temperature is better
                    score = max(0, 100 - (metric.current_value - 20) * 2)
                elif metric_name == "avg_fan_speed":
                    # Moderate fan speed is better
                    optimal_speed = 6000
                    deviation = abs(metric.current_value - optimal_speed)
                    score = max(0, 100 - deviation / 100)
                else:
                    # Higher percentage is better
                    score = metric.current_value
                
                health_scores.append(score * weight)
        
        overall_score = sum(health_scores) if health_scores else 100
        await self._update_metric("overall_health", overall_score)
    
    async def _update_metric(self, metric_name: str, value: float):
        """Update metric with new value"""
        if metric_name not in self.metrics:
            return
        
        metric = self.metrics[metric_name]
        
        # Determine status based on thresholds
        if value >= metric.threshold_critical:
            status = "critical"
        elif value >= metric.threshold_warning:
            status = "warning"
        else:
            status = "normal"
        
        point = MetricPoint(
            timestamp=datetime.now(),
            value=value,
            unit=metric.unit,
            status=status
        )
        
        metric.add_point(point)
    
    async def _broadcast_updates(self):
        """Broadcast metric updates to all connected clients"""
        if not self.websocket_connections:
            return
        
        # Prepare update data
        update_data = {
            "type": "metrics_update",
            "timestamp": datetime.now().isoformat(),
            "metrics": {}
        }
        
        for name, metric in self.metrics.items():
            update_data["metrics"][name] = {
                "current_value": metric.current_value,
                "current_status": metric.current_status,
                "trend": metric.get_trend(),
                "average_10min": metric.get_average(10),
                "max_10min": metric.get_max(10),
                "min_10min": metric.get_min(10),
                "threshold_warning": metric.threshold_warning,
                "threshold_critical": metric.threshold_critical,
                "unit": metric.unit,
                "description": metric.description
            }
        
        # Send to all connected clients
        message = json.dumps(update_data)
        disconnected = []
        
        for websocket in self.websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to WebSocket: {e}")
                disconnected.append(websocket)
        
        # Remove disconnected clients
        for ws in disconnected:
            self.websocket_connections.remove(ws)
    
    def add_websocket_connection(self, websocket):
        """Add new WebSocket connection"""
        self.websocket_connections.append(websocket)
    
    def remove_websocket_connection(self, websocket):
        """Remove WebSocket connection"""
        if websocket in self.websocket_connections:
            self.websocket_connections.remove(websocket)
    
    def get_current_metrics(self) -> Dict[str, Any]:
        """Get current snapshot of all metrics"""
        return {
            "timestamp": datetime.now().isoformat(),
            "monitoring_active": self.monitoring_active,
            "connected_clients": len(self.websocket_connections),
            "metrics": {
                name: {
                    "current_value": metric.current_value,
                    "current_status": metric.current_status,
                    "trend": metric.get_trend(),
                    "average_10min": metric.get_average(10),
                    "max_10min": metric.get_max(10),
                    "min_10min": metric.get_min(10),
                    "threshold_warning": metric.threshold_warning,
                    "threshold_critical": metric.threshold_critical,
                    "unit": metric.unit,
                    "description": metric.description,
                    "history_count": len(metric.history)
                }
                for name, metric in self.metrics.items()
            }
        }
    
    def get_metric_history(self, metric_name: str, minutes: int = 60) -> List[Dict]:
        """Get historical data for a specific metric"""
        if metric_name not in self.metrics:
            return []
        
        metric = self.metrics[metric_name]
        cutoff_time = datetime.now() - timedelta(minutes=minutes)
        
        history = [
            point.to_dict() 
            for point in metric.history 
            if point.timestamp >= cutoff_time
        ]
        
        return history
