"""
Automation Engine for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum
import json

from models.server_models import ActionLevel, ServerInfo
from core.agent_core import DellAIAgent

logger = logging.getLogger(__name__)

class TriggerType(str, Enum):
    SCHEDULE = "schedule"
    EVENT_BASED = "event_based"
    THRESHOLD = "threshold"
    MANUAL = "manual"

class WorkflowStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class WorkflowStep:
    """Individual step in a workflow"""
    name: str
    action: str
    parameters: Dict[str, Any]
    action_level: ActionLevel
    timeout: int = 300
    retry_count: int = 0
    max_retries: int = 3
    depends_on: List[str] = None
    condition: Optional[str] = None

@dataclass
class WorkflowTrigger:
    """Trigger condition for workflow execution"""
    trigger_type: TriggerType
    schedule: Optional[str] = None  # Cron expression
    event_type: Optional[str] = None
    threshold_metric: Optional[str] = None
    threshold_value: Optional[float] = None
    condition: Optional[str] = None

@dataclass
class Workflow:
    """Automation workflow definition"""
    id: str
    name: str
    description: str
    steps: List[WorkflowStep]
    trigger: WorkflowTrigger
    enabled: bool = True
    created_at: datetime = None
    last_run: Optional[datetime] = None
    status: WorkflowStatus = WorkflowStatus.PENDING

class AutomationEngine:
    """Automation engine for server management workflows"""
    
    def __init__(self, agent: DellAIAgent):
        self.agent = agent
        self.workflows: Dict[str, Workflow] = {}
        self.running_workflows: Dict[str, Dict] = {}
        self.workflow_history: List[Dict] = []
        self.scheduled_tasks: Dict[str, asyncio.Task] = {}
        
        # Built-in workflow templates
        self._initialize_builtin_workflows()
    
    def _initialize_builtin_workflows(self):
        """Initialize built-in automation workflows"""
        
        # Daily Health Check Workflow
        daily_health_check = Workflow(
            id="daily_health_check",
            name="Daily Health Check",
            description="Comprehensive daily health monitoring and reporting",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.SCHEDULE,
                schedule="0 8 * * *"  # Daily at 8 AM
            ),
            steps=[
                WorkflowStep(
                    name="collect_server_info",
                    action="get_server_info",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="health_check",
                    action="health_check",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="collect_logs",
                    action="collect_logs",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="performance_analysis",
                    action="performance_analysis",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Temperature Alert Workflow
        temperature_alert = Workflow(
            id="temperature_alert",
            name="High Temperature Alert",
            description="Automatic response to high temperature alerts",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.THRESHOLD,
                threshold_metric="temperature",
                threshold_value=80.0,
                condition="temperature > 80"
            ),
            steps=[
                WorkflowStep(
                    name="check_temperature_sensors",
                    action="get_temperature_sensors",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="check_fans",
                    action="get_fans",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="collect_logs",
                    action="collect_logs",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                )
            ]
        )
        
        # Weekly Maintenance Workflow
        weekly_maintenance = Workflow(
            id="weekly_maintenance",
            name="Weekly Maintenance",
            description="Weekly preventive maintenance tasks",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.SCHEDULE,
                schedule="0 2 * * 0"  # Sunday at 2 AM
            ),
            steps=[
                WorkflowStep(
                    name="full_health_check",
                    action="health_check",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="firmware_check",
                    action="firmware_check",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="collect_support_logs",
                    action="create_support_collection",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="export_config",
                    action="export_config",
                    parameters={"filename": "weekly_config_backup.xml"},
                    action_level=ActionLevel.FULL_CONTROL
                )
            ]
        )
        
        # Error Rate Alert Workflow
        error_alert = Workflow(
            id="error_alert",
            name="High Error Rate Alert",
            description="Response to increased error rates",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.THRESHOLD,
                threshold_metric="error_rate",
                threshold_value=0.05,
                condition="error_rate > 0.05"
            ),
            steps=[
                WorkflowStep(
                    name="collect_logs",
                    action="collect_logs",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="system_health_check",
                    action="health_check",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="troubleshoot_issues",
                    action="troubleshoot_issue",
                    parameters={
                        "issue_description": "High error rate detected in system logs",
                        "action_level": "diagnostic"
                    },
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Add built-in workflows
        for workflow in [daily_health_check, temperature_alert, weekly_maintenance, error_alert]:
            self.workflows[workflow.id] = workflow
    
    async def create_workflow(self, workflow: Workflow) -> bool:
        """Create a new automation workflow"""
        try:
            workflow.created_at = datetime.now()
            self.workflows[workflow.id] = workflow
            
            # Schedule if it's a scheduled workflow
            if workflow.trigger.trigger_type == TriggerType.SCHEDULE:
                await self._schedule_workflow(workflow)
            
            logger.info(f"Created workflow: {workflow.name}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to create workflow: {str(e)}")
            return False
    
    async def execute_workflow(self, workflow_id: str, manual_trigger: bool = False) -> bool:
        """Execute a workflow"""
        if workflow_id not in self.workflows:
            logger.error(f"Workflow not found: {workflow_id}")
            return False
        
        workflow = self.workflows[workflow_id]
        
        if not workflow.enabled and not manual_trigger:
            logger.info(f"Workflow disabled: {workflow.name}")
            return False
        
        # Check if workflow is already running
        if workflow_id in self.running_workflows:
            logger.warning(f"Workflow already running: {workflow.name}")
            return False
        
        logger.info(f"Starting workflow execution: {workflow.name}")
        
        # Initialize workflow execution context
        execution_context = {
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
            "started_at": datetime.now(),
            "status": WorkflowStatus.RUNNING,
            "steps_completed": [],
            "steps_failed": [],
            "current_step": None,
            "results": {}
        }
        
        self.running_workflows[workflow_id] = execution_context
        workflow.status = WorkflowStatus.RUNNING
        
        try:
            # Execute workflow steps
            await self._execute_workflow_steps(workflow, execution_context)
            
            # Mark as completed
            execution_context["status"] = WorkflowStatus.COMPLETED
            execution_context["completed_at"] = datetime.now()
            workflow.status = WorkflowStatus.COMPLETED
            workflow.last_run = datetime.now()
            
            logger.info(f"Workflow completed successfully: {workflow.name}")
            
        except Exception as e:
            # Mark as failed
            execution_context["status"] = WorkflowStatus.FAILED
            execution_context["error"] = str(e)
            execution_context["completed_at"] = datetime.now()
            workflow.status = WorkflowStatus.FAILED
            
            logger.error(f"Workflow failed: {workflow.name} - {str(e)}")
        
        finally:
            # Move to history
            self.workflow_history.append(execution_context.copy())
            if workflow_id in self.running_workflows:
                del self.running_workflows[workflow_id]
        
        return execution_context["status"] == WorkflowStatus.COMPLETED
    
    async def _execute_workflow_steps(self, workflow: Workflow, context: Dict):
        """Execute all steps in a workflow"""
        completed_steps = set()
        
        for step in workflow.steps:
            # Check dependencies
            if step.depends_on:
                dependencies_met = all(dep in completed_steps for dep in step.depends_on)
                if not dependencies_met:
                    logger.warning(f"Skipping step {step.name} - dependencies not met")
                    continue
            
            # Check condition
            if step.condition:
                if not await self._evaluate_condition(step.condition, context):
                    logger.info(f"Skipping step {step.name} - condition not met")
                    continue
            
            # Execute step
            context["current_step"] = step.name
            success = await self._execute_step(step, context)
            
            if success:
                completed_steps.add(step.name)
                context["steps_completed"].append(step.name)
            else:
                context["steps_failed"].append(step.name)
                if step.retry_count < step.max_retries:
                    step.retry_count += 1
                    logger.warning(f"Retrying step {step.name} (attempt {step.retry_count})")
                    # Retry the step
                    success = await self._execute_step(step, context)
                    if success:
                        completed_steps.add(step.name)
                    else:
                        logger.error(f"Step {step.name} failed after {step.max_retries} retries")
                        break
                else:
                    logger.error(f"Step {step.name} failed, stopping workflow")
                    break
    
    async def _execute_step(self, step: WorkflowStep, context: Dict) -> bool:
        """Execute a single workflow step"""
        try:
            logger.info(f"Executing step: {step.name}")
            
            # Execute the action using the agent
            result = await self.agent.execute_action(
                action_level=step.action_level,
                command=step.action,
                parameters=step.parameters
            )
            
            # Store result
            context["results"][step.name] = result
            
            logger.info(f"Step completed: {step.name}")
            return True
            
        except Exception as e:
            logger.error(f"Step failed: {step.name} - {str(e)}")
            context["results"][step.name] = {"error": str(e)}
            return False
    
    async def _evaluate_condition(self, condition: str, context: Dict) -> bool:
        """Evaluate a condition expression"""
        try:
            # Simple condition evaluation
            # In a production system, use a proper expression parser
            
            # Replace common variables
            condition_vars = {
                "previous_results": context.get("results", {}),
                "steps_completed": context.get("steps_completed", [])
            }
            
            # For now, implement basic conditions
            if "previous_step_success" in condition:
                # Check if previous step was successful
                return len(context.get("steps_completed", [])) > 0
            
            return True  # Default to true if condition can't be evaluated
            
        except Exception as e:
            logger.error(f"Condition evaluation failed: {str(e)}")
            return False
    
    async def _schedule_workflow(self, workflow: Workflow):
        """Schedule a workflow for automatic execution"""
        if workflow.trigger.trigger_type != TriggerType.SCHEDULE:
            return
        
        # For now, implement simple scheduling
        # In production, use a proper cron scheduler
        schedule_interval = self._parse_schedule(workflow.trigger.schedule)
        
        if schedule_interval:
            task = asyncio.create_task(self._run_scheduled_workflow(workflow, schedule_interval))
            self.scheduled_tasks[workflow.id] = task
    
    def _parse_schedule(self, schedule: str) -> Optional[timedelta]:
        """Parse simple schedule expressions"""
        # Basic implementation - in production use cron parser
        if schedule == "0 8 * * *":  # Daily at 8 AM
            return timedelta(hours=24)
        elif schedule == "0 2 * * 0":  # Sunday at 2 AM
            return timedelta(days=7)
        elif schedule == "0 * * * *":  # Hourly
            return timedelta(hours=1)
        return None
    
    async def _run_scheduled_workflow(self, workflow: Workflow, interval: timedelta):
        """Run a workflow on a schedule"""
        while workflow.enabled:
            try:
                await asyncio.sleep(interval.total_seconds())
                if workflow.enabled:
                    await self.execute_workflow(workflow.id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduled workflow error: {str(e)}")
    
    async def trigger_event_workflow(self, event_type: str, event_data: Dict[str, Any]):
        """Trigger workflows based on events"""
        for workflow_id, workflow in self.workflows.items():
            if (workflow.enabled and 
                workflow.trigger.trigger_type == TriggerType.EVENT_BASED and
                workflow.trigger.event_type == event_type):
                
                logger.info(f"Triggering event-based workflow: {workflow.name}")
                await self.execute_workflow(workflow_id)
    
    async def trigger_threshold_workflow(self, metric: str, value: float):
        """Trigger workflows based on threshold violations"""
        for workflow_id, workflow in self.workflows.items():
            if (workflow.enabled and 
                workflow.trigger.trigger_type == TriggerType.THRESHOLD and
                workflow.trigger.threshold_metric == metric):
                
                threshold = workflow.trigger.threshold_value
                condition = workflow.trigger.condition
                
                # Check threshold condition
                trigger_workflow = False
                if condition and ">" in condition:
                    trigger_workflow = value > threshold
                elif condition and "<" in condition:
                    trigger_workflow = value < threshold
                
                if trigger_workflow:
                    logger.info(f"Triggering threshold-based workflow: {workflow.name}")
                    await self.execute_workflow(workflow_id)
    
    def get_workflow_status(self, workflow_id: str) -> Optional[Dict]:
        """Get status of a specific workflow"""
        if workflow_id in self.running_workflows:
            return self.running_workflows[workflow_id]
        
        if workflow_id in self.workflows:
            workflow = self.workflows[workflow_id]
            return {
                "workflow_id": workflow_id,
                "workflow_name": workflow.name,
                "status": workflow.status,
                "last_run": workflow.last_run,
                "enabled": workflow.enabled
            }
        
        return None
    
    def get_all_workflows(self) -> List[Dict]:
        """Get all workflows with their status"""
        workflows = []
        for workflow_id, workflow in self.workflows.items():
            workflows.append({
                "id": workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "status": workflow.status,
                "enabled": workflow.enabled,
                "trigger_type": workflow.trigger.trigger_type,
                "last_run": workflow.last_run,
                "created_at": workflow.created_at,
                "step_count": len(workflow.steps)
            })
        return workflows
    
    def get_workflow_history(self, limit: int = 50) -> List[Dict]:
        """Get workflow execution history"""
        return self.workflow_history[-limit:] if self.workflow_history else []
    
    async def enable_workflow(self, workflow_id: str) -> bool:
        """Enable a workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].enabled = True
            
            # Schedule if it's a scheduled workflow
            workflow = self.workflows[workflow_id]
            if workflow.trigger.trigger_type == TriggerType.SCHEDULE:
                await self._schedule_workflow(workflow)
            
            return True
        return False
    
    async def disable_workflow(self, workflow_id: str) -> bool:
        """Disable a workflow"""
        if workflow_id in self.workflows:
            self.workflows[workflow_id].enabled = False
            
            # Cancel scheduled task
            if workflow_id in self.scheduled_tasks:
                self.scheduled_tasks[workflow_id].cancel()
                del self.scheduled_tasks[workflow_id]
            
            return True
        return False
    
    async def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow"""
        if workflow_id in self.workflows:
            # Disable first
            await self.disable_workflow(workflow_id)
            
            # Remove from workflows
            del self.workflows[workflow_id]
            
            logger.info(f"Deleted workflow: {workflow_id}")
            return True
        return False
    
    def get_running_workflows(self) -> List[Dict]:
        """Get currently running workflows"""
        return list(self.running_workflows.values())
    
    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel a running workflow"""
        if workflow_id in self.running_workflows:
            context = self.running_workflows[workflow_id]
            context["status"] = WorkflowStatus.CANCELLED
            context["cancelled_at"] = datetime.now()
            
            # Update workflow status
            if workflow_id in self.workflows:
                self.workflows[workflow_id].status = WorkflowStatus.CANCELLED
            
            # Remove from running workflows
            del self.running_workflows[workflow_id]
            
            logger.info(f"Cancelled workflow: {workflow_id}")
            return True
        
        return False
