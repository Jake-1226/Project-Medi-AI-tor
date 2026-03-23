"""
Field Technician Specific Workflows for Dell Server AI Agent
"""

import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass
from enum import Enum

from core.automation_engine import Workflow, WorkflowStep, WorkflowTrigger, TriggerType
from models.server_models import ActionLevel

logger = logging.getLogger(__name__)

class TechnicianTaskType(str, Enum):
    INSTALLATION = "installation"
    MAINTENANCE = "maintenance"
    TROUBLESHOOTING = "troubleshooting"
    UPGRADE = "upgrade"
    REPLACEMENT = "replacement"
    INSPECTION = "inspection"

@dataclass
class TechnicianTask:
    """Field technician task definition"""
    task_id: str
    task_type: TechnicianTaskType
    title: str
    description: str
    priority: str  # low, medium, high, critical
    estimated_duration: int  # in minutes
    required_skills: List[str]
    required_tools: List[str]
    required_parts: List[str]
    safety_precautions: List[str]
    steps: List[str]
    verification_steps: List[str]
    documentation: List[str]

class FieldTechnicianWorkflows:
    """Field technician specific workflow manager"""
    
    def __init__(self):
        self.technician_tasks: Dict[str, TechnicianTask] = {}
        self.workflows: Dict[str, Workflow] = {}
        self.active_tasks: Dict[str, Dict] = {}
        
        # Initialize built-in technician workflows
        self._initialize_technician_workflows()
    
    def _initialize_technician_workflows(self):
        """Initialize field technician specific workflows"""
        
        # Server Installation Workflow
        server_installation = Workflow(
            id="server_installation",
            name="Server Installation - Field Technician",
            description="Complete server installation workflow for field technicians",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.MANUAL
            ),
            steps=[
                WorkflowStep(
                    name="pre_installation_checklist",
                    action="pre_installation_validation",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="rack_preparation",
                    action="rack_preparation_check",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="hardware_installation",
                    action="hardware_installation_guide",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="cabling_and_connectivity",
                    action="cabling_verification",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="power_on_initialization",
                    action="power_on_sequence",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="idrac_configuration",
                    action="idrac_setup",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="post_installation_verification",
                    action="installation_verification",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Memory Replacement Workflow
        memory_replacement = Workflow(
            id="memory_replacement",
            name="Memory Module Replacement - Field Technician",
            description="Memory module replacement workflow for field technicians",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.EVENT_BASED,
                event_type="memory_failure_detected"
            ),
            steps=[
                WorkflowStep(
                    name="memory_diagnostic",
                    action="memory_module_test",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="power_down_preparation",
                    action="safe_power_down",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="esd_safety_preparation",
                    action="esd_safety_check",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="memory_replacement",
                    action="replace_memory_modules",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="post_replacement_test",
                    action="memory_verification_test",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="documentation_update",
                    action="update_hardware_inventory",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Power Supply Replacement Workflow
        psu_replacement = Workflow(
            id="psu_replacement",
            name="Power Supply Replacement - Field Technician",
            description="Power supply unit replacement workflow for field technicians",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.EVENT_BASED,
                event_type="power_supply_failure"
            ),
            steps=[
                WorkflowStep(
                    name="psu_diagnostic",
                    action="power_supply_diagnostic",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="power_safety_check",
                    action="electrical_safety_verification",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="power_down_isolation",
                    action="safe_power_isolation",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="psu_replacement",
                    action="replace_power_supply",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="power_verification",
                    action="power_system_verification",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="redundancy_test",
                    action="power_redundancy_test",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Hard Drive Replacement Workflow
        hdd_replacement = Workflow(
            id="hdd_replacement",
            name="Hard Drive Replacement - Field Technician",
            description="Hard drive replacement workflow for field technicians",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.EVENT_BASED,
                event_type="drive_failure"
            ),
            steps=[
                WorkflowStep(
                    name="drive_identification",
                    action="identify_failed_drive",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="raid_status_check",
                    action="raid_array_status",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="data_backup_verification",
                    action="verify_data_backup",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="drive_replacement",
                    action="replace_hard_drive",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="raid_rebuild",
                    action="initiate_raid_rebuild",
                    parameters={},
                    action_level=ActionLevel.FULL_CONTROL
                ),
                WorkflowStep(
                    name="rebuild_monitoring",
                    action="monitor_raid_rebuild",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                )
            ]
        )
        
        # Preventive Maintenance Workflow
        preventive_maintenance = Workflow(
            id="preventive_maintenance",
            name="Preventive Maintenance - Field Technician",
            description="Comprehensive preventive maintenance workflow",
            trigger=WorkflowTrigger(
                trigger_type=TriggerType.SCHEDULE,
                schedule="0 2 1 * *"  # First of month at 2 AM
            ),
            steps=[
                WorkflowStep(
                    name="visual_inspection",
                    action="visual_hardware_inspection",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                ),
                WorkflowStep(
                    name="cooling_system_check",
                    action="cooling_system_verification",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="firmware_update_check",
                    action="firmware_version_check",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="diagnostic_tests",
                    action="comprehensive_diagnostics",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="calibration_verification",
                    action="sensor_calibration_check",
                    parameters={},
                    action_level=ActionLevel.DIAGNOSTIC
                ),
                WorkflowStep(
                    name="maintenance_report",
                    action="generate_maintenance_report",
                    parameters={},
                    action_level=ActionLevel.READ_ONLY
                )
            ]
        )
        
        # Add workflows to registry
        for workflow in [server_installation, memory_replacement, psu_replacement, hdd_replacement, preventive_maintenance]:
            self.workflows[workflow.id] = workflow
    
    def get_technician_task(self, task_id: str) -> Optional[TechnicianTask]:
        """Get technician task by ID"""
        return self.technician_tasks.get(task_id)
    
    def create_technician_task(self, task: TechnicianTask) -> str:
        """Create a new technician task"""
        self.technician_tasks[task.task_id] = task
        logger.info(f"Created technician task: {task.task_id}")
        return task.task_id
    
    def get_workflows_for_technician(self) -> List[Dict[str, Any]]:
        """Get all workflows suitable for field technicians"""
        technician_workflows = []
        
        for workflow_id, workflow in self.workflows.items():
            workflow_info = {
                "id": workflow_id,
                "name": workflow.name,
                "description": workflow.description,
                "trigger_type": workflow.trigger.trigger_type,
                "step_count": len(workflow.steps),
                "estimated_duration": self._estimate_workflow_duration(workflow),
                "required_skills": self._get_workflow_skills(workflow),
                "required_tools": self._get_workflow_tools(workflow),
                "safety_level": self._get_workflow_safety_level(workflow)
            }
            technician_workflows.append(workflow_info)
        
        return technician_workflows
    
    def _estimate_workflow_duration(self, workflow: Workflow) -> int:
        """Estimate workflow duration in minutes"""
        duration_map = {
            "pre_installation_checklist": 15,
            "rack_preparation": 30,
            "hardware_installation": 60,
            "cabling_and_connectivity": 45,
            "power_on_initialization": 20,
            "idrac_configuration": 15,
            "post_installation_verification": 30,
            "memory_diagnostic": 20,
            "power_down_preparation": 10,
            "esd_safety_preparation": 5,
            "memory_replacement": 30,
            "post_replacement_test": 25,
            "documentation_update": 10,
            "psu_diagnostic": 15,
            "power_safety_check": 10,
            "power_down_isolation": 15,
            "psu_replacement": 45,
            "power_verification": 20,
            "redundancy_test": 15,
            "drive_identification": 10,
            "raid_status_check": 15,
            "data_backup_verification": 20,
            "drive_replacement": 40,
            "raid_rebuild": 10,
            "rebuild_monitoring": 30,
            "visual_inspection": 20,
            "cooling_system_check": 25,
            "firmware_update_check": 15,
            "diagnostic_tests": 45,
            "calibration_verification": 20,
            "maintenance_report": 15
        }
        
        total_duration = 0
        for step in workflow.steps:
            total_duration += duration_map.get(step.action, 30)  # Default 30 minutes
        
        return total_duration
    
    def _get_workflow_skills(self, workflow: Workflow) -> List[str]:
        """Get required skills for a workflow"""
        skills_map = {
            "hardware_installation": ["Server Hardware Installation", "Rack Mounting"],
            "memory_replacement": ["Memory Module Replacement", "ESD Safety"],
            "replace_power_supply": ["Electrical Safety", "Power Supply Installation"],
            "replace_hard_drive": ["Storage Installation", "RAID Configuration"],
            "cabling_verification": ["Network Cabling", "Fiber Optic Termination"],
            "idrac_setup": ["iDRAC Configuration", "Network Configuration"]
        }
        
        required_skills = set()
        for step in workflow.steps:
            step_skills = skills_map.get(step.action, [])
            required_skills.update(step_skills)
        
        return list(required_skills)
    
    def _get_workflow_tools(self, workflow: Workflow) -> List[str]:
        """Get required tools for a workflow"""
        tools_map = {
            "hardware_installation": ["Screwdrivers", "Torx bits", "Rack rails", "Cable management"],
            "memory_replacement": ["Anti-static wrist strap", "Memory module extractors", "Compressed air"],
            "replace_power_supply": ["Multimeter", "Screwdrivers", "Cable management", "Power tester"],
            "replace_hard_drive": ["Screwdrivers", "Hard drive trays", "Cable management"],
            "cabling_verification": ["Cable tester", "Network cable tester", "Fiber optic tester"],
            "cooling_system_verification": ["Temperature probe", "Airflow meter", "Cleaning supplies"]
        }
        
        required_tools = set()
        for step in workflow.steps:
            step_tools = tools_map.get(step.action, [])
            required_tools.update(step_tools)
        
        return list(required_tools)
    
    def _get_workflow_safety_level(self, workflow: Workflow) -> str:
        """Get safety level for a workflow"""
        high_risk_actions = [
            "replace_power_supply",
            "power_down_isolation",
            "electrical_safety_verification"
        ]
        
        medium_risk_actions = [
            "hardware_installation",
            "memory_replacement",
            "replace_hard_drive"
        ]
        
        for step in workflow.steps:
            if step.action in high_risk_actions:
                return "HIGH"
            elif step.action in medium_risk_actions:
                return "MEDIUM"
        
        return "LOW"
    
    def create_field_service_report(self, task_id: str, technician_id: str, 
                                   findings: Dict[str, Any], actions_taken: List[str]) -> Dict[str, Any]:
        """Create field service report"""
        task = self.get_technician_task(task_id)
        if not task:
            return {"error": "Task not found"}
        
        report = {
            "report_id": f"fsr_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            "task_id": task_id,
            "technician_id": technician_id,
            "task_type": task.task_type,
            "task_title": task.title,
            "start_time": datetime.now().isoformat(),
            "findings": findings,
            "actions_taken": actions_taken,
            "parts_used": task.required_parts,
            "tools_used": task.required_tools,
            "safety_precautions_followed": task.safety_precautions,
            "verification_completed": False,
            "customer_signature": None,
            "notes": ""
        }
        
        return report
    
    def get_safety_checklist(self, task_type: TechnicianTaskType) -> List[str]:
        """Get safety checklist for task type"""
        safety_checklists = {
            TechnicianTaskType.INSTALLATION: [
                "Verify power is OFF before beginning work",
                "Use proper lifting techniques for heavy equipment",
                "Ensure rack is properly secured and stable",
                "Wear appropriate PPE (gloves, safety glasses)",
                "Verify electrical outlets are properly grounded",
                "Check for sharp edges on rack equipment",
                "Ensure adequate ventilation in work area",
                "Keep work area clean and organized"
            ],
            TechnicianTaskType.MAINTENANCE: [
                "Verify system is powered down before opening case",
                "Use anti-static protection (wrist strap, mat)",
                "Disconnect all power sources before internal work",
                "Wear appropriate PPE for the task",
                "Check for hot surfaces before touching components",
                "Use proper tools for each task",
                "Follow manufacturer guidelines for all procedures",
                "Document any abnormalities found during maintenance"
            ],
            TechnicianTaskType.REPLACEMENT: [
                "Verify system is powered down and unplugged",
                "Use anti-static protection for all electronic components",
                "Wear appropriate PPE (gloves, safety glasses)",
                "Handle components by edges only",
                "Use proper tools for component removal/installation",
                "Verify replacement part compatibility before installation",
                "Test system after replacement is complete",
                "Dispose of old components according to regulations"
            ],
            TechnicianTaskType.UPGRADE: [
                "Verify system compatibility before upgrade",
                "Backup critical data before beginning upgrade",
                "Use anti-static protection for all components",
                "Follow manufacturer upgrade procedures exactly",
                "Verify all connections after upgrade",
                "Test upgraded functionality thoroughly",
                "Update system documentation after upgrade",
                "Provide upgrade summary to system owner"
            ]
        }
        
        return safety_checklists.get(task_type, [
            "Follow general safety procedures",
            "Wear appropriate PPE",
            "Use proper tools for the task",
            "Document all work performed"
        ])
    
    def get_troubleshooting_guides(self) -> Dict[str, Dict[str, Any]]:
        """Get troubleshooting guides for common field issues"""
        
        return {
            "server_no_power": {
                "title": "Server Will Not Power On",
                "symptoms": ["No LED lights", "No fan spin", "No display"],
                "causes": [
                    "Power supply failure",
                    "Power cable disconnected",
                    "Circuit breaker tripped",
                    "Motherboard failure",
                    "Power button failure"
                ],
                "troubleshooting_steps": [
                    "Check power cable connection at both ends",
                    "Verify outlet has power (test with known good device)",
                    "Check circuit breaker or power strip",
                    "Try different power outlet",
                    "Verify power supply switch is ON",
                    "Check for visible damage to power supply",
                    "Test with known good power supply if available"
                ],
                "tools_required": ["Multimeter", "Screwdrivers", "Known good power cable"],
                "safety_notes": ["Always disconnect power before opening case", "Check for capacitors that may hold charge"]
            },
            
            "overheating_issues": {
                "title": "Server Overheating",
                "symptoms": ["High temperature warnings", "Fan running at high speed", "System shutdowns"],
                "causes": [
                    "Dust accumulation in fans and heat sinks",
                    "Failed fan or fan controller",
                    "Blocked air vents",
                    "Ambient temperature too high",
                    "Thermal paste degradation",
                    "Failed temperature sensor"
                ],
                "troubleshooting_steps": [
                    "Check all air vents for blockages",
                    "Clean dust from fans and heat sinks",
                    "Verify all fans are spinning",
                    "Check ambient room temperature",
                    "Monitor temperature sensors in iDRAC",
                    "Check for failed thermal sensors",
                    "Verify heat sink contact with CPU"
                ],
                "tools_required": ["Compressed air", "Temperature probe", "Screwdrivers"],
                "safety_notes": ["Allow system to cool before opening case", "Be careful with compressed air around sensitive components"]
            },
            
            "memory_errors": {
                "title": "Memory Errors Detected",
                "symptoms": ["Blue screen crashes", "System instability", "Memory error messages"],
                "causes": [
                    "Failed memory module",
                    "Incorrect memory configuration",
                    "Memory slot failure",
                    "Incompatible memory modules",
                    "Memory timing issues",
                    "Motherboard memory controller failure"
                ],
                "troubleshooting_steps": [
                    "Run comprehensive memory diagnostics",
                    "Check memory module seating",
                    "Test modules individually",
                    "Verify memory compatibility",
                    "Check BIOS memory settings",
                    "Test different memory slots",
                    "Update BIOS if available"
                ],
                "tools_required": ["Memory diagnostic software", "Anti-static wrist strap", "Screwdrivers"],
                "safety_notes": ["Always use anti-static protection when handling memory", "Power down completely before removing modules"]
            },
            
            "storage_issues": {
                "title": "Storage/RAID Issues",
                "symptoms": ["Drive failure warnings", "RAID degraded status", "Slow disk performance"],
                "causes": [
                    "Failed hard drive",
                    "RAID controller failure",
                    "Cable connectivity issues",
                    "Power supply issues to drives",
                    "Configuration errors",
                    "Firmware issues"
                ],
                "troubleshooting_steps": [
                    "Check RAID controller status in iDRAC",
                    "Identify failed drive from controller logs",
                    "Verify all drive connections",
                    "Check drive power and data cables",
                    "Run drive diagnostics",
                    "Verify RAID configuration",
                    "Update controller firmware if needed"
                ],
                "tools_required": ["Screwdrivers", "Diagnostic software", "Replacement cables"],
                "safety_notes": ["Handle drives carefully", "Back up data before replacing drives", "Follow ESD precautions"]
            }
        }
    
    def get_parts_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Get parts catalog for common replacements"""
        
        return {
            "memory_modules": {
                "ddr4_16gb": {
                    "part_number": "370-ADQK",
                    "description": "16GB DDR4 2666MHz ECC RAM",
                    "compatible_models": ["PowerEdge R640", "PowerEdge R740", "PowerEdge R740xd"],
                    "quantity_per_server": 16,
                    "installation_notes": "Install in pairs for optimal performance"
                },
                "ddr4_32gb": {
                    "part_number": "370-AERJ",
                    "description": "32GB DDR4 2666MHz ECC RAM",
                    "compatible_models": ["PowerEdge R640", "PowerEdge R740", "PowerEdge R740xd"],
                    "quantity_per_server": 16,
                    "installation_notes": "Check BIOS compatibility for larger modules"
                }
            },
            "power_supplies": {
                "psu_750w": {
                    "part_number": "450-AEJF",
                    "description": "750W Power Supply Unit",
                    "compatible_models": ["PowerEdge R640", "PowerEdge R740"],
                    "quantity_per_server": 2,
                    "installation_notes": "Verify power redundancy configuration"
                },
                "psu_1100w": {
                    "part_number": "450-AEJG",
                    "description": "1100W Power Supply Unit",
                    "compatible_models": ["PowerEdge R740xd", "PowerEdge T640"],
                    "quantity_per_server": 2,
                    "installation_notes": "Ensure adequate cooling for higher wattage"
                }
            },
            "hard_drives": {
                "hdd_1tb_sata": {
                    "part_number": "400-ATFO",
                    "description": "1TB 7.2K SATA HDD",
                    "compatible_models": ["All PowerEdge servers"],
                    "quantity_per_server": "Varies by configuration",
                    "installation_notes": "Check RAID configuration before replacement"
                },
                "ssd_480gb_sata": {
                    "part_number": "400-ATFP",
                    "description": "480GB SATA SSD",
                    "compatible_models": ["All PowerEdge servers"],
                    "quantity_per_server": "Varies by configuration",
                    "installation_notes": "Faster performance for boot and applications"
                }
            },
            "cooling_components": {
                "fan_80mm": {
                    "part_number": "JHFPF",
                    "description": "80mm System Fan",
                    "compatible_models": ["PowerEdge R640", "PowerEdge R740"],
                    "quantity_per_server": 4,
                    "installation_notes": "Check fan speed after replacement"
                },
                "heatsink_cpu": {
                    "part_number": "0M9TTH",
                    "description": "CPU Heatsink Assembly",
                    "compatible_models": ["PowerEdge R640", "PowerEdge R740"],
                    "quantity_per_server": 2,
                    "installation_notes": "Apply new thermal paste during replacement"
                }
            }
        }
