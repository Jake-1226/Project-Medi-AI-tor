"""
Role-Based Access Control (RBAC) for Medi-AI-tor.
Manages user permissions and access control for different operation levels.
"""

import asyncio
import logging
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import hashlib
import secrets

logger = logging.getLogger(__name__)

class Permission(Enum):
    """System permissions"""
    READ_ONLY = "read_only"
    DIAGNOSTIC = "diagnostic"
    FULL_CONTROL = "full_control"
    ADMIN = "admin"
    WEBHOOK_MANAGE = "webhook_manage"
    USER_MANAGE = "user_manage"
    SYSTEM_CONFIG = "system_config"

class Role(Enum):
    """User roles with predefined permission sets"""
    VIEWER = "viewer"
    OPERATOR = "operator"
    TECHNICIAN = "technician"
    ADMIN = "admin"
    SUPER_ADMIN = "super_admin"

@dataclass
class User:
    """User account with roles and permissions"""
    username: str
    email: str
    roles: Set[Role]
    permissions: Set[Permission]
    created_at: datetime
    last_login: Optional[datetime] = None
    active: bool = True
    session_token: Optional[str] = None
    session_expires: Optional[datetime] = None
    
    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission"""
        return permission in self.permissions
    
    def has_any_permission(self, permissions: List[Permission]) -> bool:
        """Check if user has any of the specified permissions"""
        return any(p in self.permissions for p in permissions)
    
    def has_role(self, role: Role) -> bool:
        """Check if user has a specific role"""
        return role in self.roles
    
    def is_session_valid(self) -> bool:
        """Check if user session is still valid"""
        if not self.session_token or not self.session_expires:
            return False
        return datetime.utcnow() < self.session_expires

@dataclass
class AccessPolicy:
    """Access policy for specific resources"""
    resource: str
    required_permissions: List[Permission]
    allowed_roles: List[Role]
    description: str

class RBACManager:
    """Role-Based Access Control manager"""
    
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.role_permissions: Dict[Role, Set[Permission]] = {}
        self.access_policies: Dict[str, AccessPolicy] = {}
        self.session_timeout_hours = 8
        
        self._setup_default_roles()
        self._setup_default_policies()
    
    def _setup_default_roles(self):
        """Setup default role permissions"""
        self.role_permissions = {
            Role.VIEWER: {
                Permission.READ_ONLY,
            },
            Role.OPERATOR: {
                Permission.READ_ONLY,
                Permission.DIAGNOSTIC,
            },
            Role.TECHNICIAN: {
                Permission.READ_ONLY,
                Permission.DIAGNOSTIC,
                Permission.FULL_CONTROL,
            },
            Role.ADMIN: {
                Permission.READ_ONLY,
                Permission.DIAGNOSTIC,
                Permission.FULL_CONTROL,
                Permission.WEBHOOK_MANAGE,
                Permission.USER_MANAGE,
            },
            Role.SUPER_ADMIN: {
                Permission.READ_ONLY,
                Permission.DIAGNOSTIC,
                Permission.FULL_CONTROL,
                Permission.WEBHOOK_MANAGE,
                Permission.USER_MANAGE,
                Permission.SYSTEM_CONFIG,
                Permission.ADMIN,
            }
        }
    
    def _setup_default_policies(self):
        """Setup default access policies"""
        self.access_policies = {
            "server_connect": AccessPolicy(
                resource="server_connect",
                required_permissions=[Permission.READ_ONLY],
                allowed_roles=[Role.VIEWER, Role.OPERATOR, Role.TECHNICIAN, Role.ADMIN, Role.SUPER_ADMIN],
                description="Connect to a server"
            ),
            "investigate": AccessPolicy(
                resource="investigate",
                required_permissions=[Permission.READ_ONLY],
                allowed_roles=[Role.VIEWER, Role.OPERATOR, Role.TECHNICIAN, Role.ADMIN, Role.SUPER_ADMIN],
                description="Run AI investigation"
            ),
            "diagnostic_commands": AccessPolicy(
                resource="diagnostic_commands",
                required_permissions=[Permission.DIAGNOSTIC],
                allowed_roles=[Role.OPERATOR, Role.TECHNICIAN, Role.ADMIN, Role.SUPER_ADMIN],
                description="Run diagnostic commands (ePSA, TSR collection)"
            ),
            "full_control_commands": AccessPolicy(
                resource="full_control_commands",
                required_permissions=[Permission.FULL_CONTROL],
                allowed_roles=[Role.TECHNICIAN, Role.ADMIN, Role.SUPER_ADMIN],
                description="Run full control commands (reboot, BIOS changes, firmware updates)"
            ),
            "webhook_management": AccessPolicy(
                resource="webhook_management",
                required_permissions=[Permission.WEBHOOK_MANAGE],
                allowed_roles=[Role.ADMIN, Role.SUPER_ADMIN],
                description="Manage webhook endpoints"
            ),
            "user_management": AccessPolicy(
                resource="user_management",
                required_permissions=[Permission.USER_MANAGE],
                allowed_roles=[Role.ADMIN, Role.SUPER_ADMIN],
                description="Manage user accounts"
            ),
            "system_configuration": AccessPolicy(
                resource="system_configuration",
                required_permissions=[Permission.SYSTEM_CONFIG],
                allowed_roles=[Role.SUPER_ADMIN],
                description="Modify system configuration"
            )
        }
    
    def create_user(self, username: str, email: str, roles: List[Role]) -> User:
        """Create a new user account"""
        if username in self.users:
            raise ValueError(f"User {username} already exists")
        
        # Calculate permissions from roles
        permissions = set()
        for role in roles:
            permissions.update(self.role_permissions.get(role, set()))
        
        user = User(
            username=username,
            email=email,
            roles=set(roles),
            permissions=permissions,
            created_at=datetime.utcnow()
        )
        
        self.users[username] = user
        logger.info(f"Created user {username} with roles {[r.value for r in roles]}")
        return user
    
    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return session token"""
        user = self.users.get(username)
        if not user or not user.active:
            return None
        
        # In a real implementation, you'd hash and verify password
        # For demo purposes, we'll accept any password for existing users
        
        # Generate session token
        session_token = secrets.token_urlsafe(32)
        user.session_token = session_token
        user.session_expires = datetime.utcnow() + timedelta(hours=self.session_timeout_hours)
        user.last_login = datetime.utcnow()
        
        logger.info(f"User {username} authenticated successfully")
        return session_token
    
    def validate_session(self, username: str, session_token: str) -> bool:
        """Validate user session token"""
        user = self.users.get(username)
        if not user:
            return False
        
        return user.session_token == session_token and user.is_session_valid()
    
    def check_permission(self, username: str, resource: str, session_token: Optional[str] = None) -> bool:
        """Check if user has permission to access a resource"""
        user = self.users.get(username)
        if not user or not user.active:
            return False
        
        # Validate session if provided
        if session_token and not self.validate_session(username, session_token):
            return False
        
        # Get access policy for resource
        policy = self.access_policies.get(resource)
        if not policy:
            logger.warning(f"No access policy found for resource: {resource}")
            return False
        
        # Check if user has any required permission
        if user.has_any_permission(policy.required_permissions):
            return True
        
        # Check if user has any allowed role
        if any(user.has_role(role) for role in policy.allowed_roles):
            return True
        
        return False
    
    def get_user_permissions(self, username: str) -> Set[Permission]:
        """Get all permissions for a user"""
        user = self.users.get(username)
        if not user:
            return set()
        return user.permissions
    
    def add_role_to_user(self, username: str, role: Role) -> bool:
        """Add a role to a user"""
        user = self.users.get(username)
        if not user:
            return False
        
        if role in user.roles:
            return True  # Already has role
        
        user.roles.add(role)
        user.permissions.update(self.role_permissions.get(role, set()))
        
        logger.info(f"Added role {role.value} to user {username}")
        return True
    
    def remove_role_from_user(self, username: str, role: Role) -> bool:
        """Remove a role from a user"""
        user = self.users.get(username)
        if not user:
            return False
        
        if role not in user.roles:
            return True  # Doesn't have role
        
        user.roles.remove(role)
        
        # Recalculate permissions
        user.permissions = set()
        for r in user.roles:
            user.permissions.update(self.role_permissions.get(r, set()))
        
        logger.info(f"Removed role {role.value} from user {username}")
        return True
    
    def deactivate_user(self, username: str) -> bool:
        """Deactivate a user account"""
        user = self.users.get(username)
        if not user:
            return False
        
        user.active = False
        user.session_token = None
        user.session_expires = None
        
        logger.info(f"Deactivated user {username}")
        return True
    
    def get_access_log(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        """Get access log for a user (simplified implementation)"""
        # In a real implementation, you'd store access logs in a database
        return [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "username": username,
                "resource": "server_connect",
                "action": "access_granted",
                "ip_address": "127.0.0.1"
            }
        ]
    
    def get_user_summary(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user summary information"""
        user = self.users.get(username)
        if not user:
            return None
        
        return {
            "username": user.username,
            "email": user.email,
            "roles": [r.value for r in user.roles],
            "permissions": [p.value for p in user.permissions],
            "created_at": user.created_at.isoformat(),
            "last_login": user.last_login.isoformat() if user.last_login else None,
            "active": user.active,
            "session_valid": user.is_session_valid()
        }
    
    def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions"""
        expired_count = 0
        for user in self.users.values():
            if user.session_expires and datetime.utcnow() > user.session_expires:
                user.session_token = None
                user.session_expires = None
                expired_count += 1
        
        if expired_count > 0:
            logger.info(f"Cleaned up {expired_count} expired sessions")
        
        return expired_count

# Global RBAC manager instance
rbac_manager = RBACManager()

# Create default users for demo
def setup_demo_users():
    """Setup demo users for testing"""
    try:
        rbac_manager.create_user("viewer", "viewer@example.com", [Role.VIEWER])
        rbac_manager.create_user("operator", "operator@example.com", [Role.OPERATOR])
        rbac_manager.create_user("tech", "tech@example.com", [Role.TECHNICIAN])
        rbac_manager.create_user("admin", "admin@example.com", [Role.ADMIN])
        rbac_manager.create_user("super", "super@example.com", [Role.SUPER_ADMIN])
        logger.info("Demo users created successfully")
    except Exception as e:
        logger.error(f"Failed to create demo users: {e}")

# Auto-setup demo users
setup_demo_users()
