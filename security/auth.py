"""
Authentication and authorization for Dell Server AI Agent
"""

import hashlib
import secrets
import logging
import os
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import jwt
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

from core.config import AgentConfig

logger = logging.getLogger(__name__)

# Default passwords are NEVER hardcoded — they are loaded from environment
# variables at startup. If not set, cryptographically random passwords are
# generated and logged (once) so the operator can use them.
_ENV_PASSWORD_KEYS = {
    "admin":    "AUTH_ADMIN_PASSWORD",
    "operator": "AUTH_OPERATOR_PASSWORD",
    "viewer":   "AUTH_VIEWER_PASSWORD",
}

class AuthenticationError(Exception):
    """Authentication failed exception"""
    pass

class AuthorizationError(Exception):
    """Authorization failed exception"""
    pass

class AuthManager:
    """Authentication and authorization manager"""
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.secret_key = self._generate_secret_key()
        self.token_expiry = timedelta(hours=1)         # Short-lived access token
        self.refresh_expiry = timedelta(hours=24)       # Longer-lived refresh token
        self.failed_attempts = {}  # Track failed login attempts
        self.max_attempts = 20
        self.lockout_duration = timedelta(minutes=5)
        
        # User store — passwords loaded from environment variables, never hardcoded
        self.users = {}
        _role_perms = {
            "admin":    ["read_only", "diagnostic", "full_control"],
            "operator": ["read_only", "diagnostic"],
            "viewer":   ["read_only"],
        }
        for role, env_key in _ENV_PASSWORD_KEYS.items():
            pw = os.getenv(env_key, "")
            if not pw:
                pw = secrets.token_urlsafe(16)
                logger.warning(
                    f"No {env_key} set — generated random password for '{role}': {pw}  "
                    f"(set {env_key} in environment to use a fixed password)"
                )
            self.users[role] = {
                "password_hash": self._hash_password(pw),
                "role": role,
                "permissions": _role_perms[role],
                "created_at": datetime.now(),
                "last_login": None,
                "active": True,
            }
        
        # Session store
        self.sessions = {}
        
        # Initialize encryption
        self.encryption_key = self._generate_encryption_key()
        self.cipher = Fernet(self.encryption_key)
    
    def _generate_secret_key(self) -> str:
        """Get secret key from env (shared across workers) or generate random."""
        return os.getenv('SECRET_KEY', '') or secrets.token_urlsafe(32)
    
    def _generate_encryption_key(self) -> bytes:
        """Generate encryption key for sensitive data"""
        password = self.secret_key.encode()
        # Salt from environment or auto-generated per deployment
        salt = os.getenv("ENCRYPTION_SALT", "").encode() or secrets.token_bytes(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password))
        return key
    
    def _hash_password(self, password: str) -> str:
        """Hash password using SHA-256 with salt"""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"
    
    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify password against hash"""
        try:
            salt, hash_value = password_hash.split(':')
            computed_hash = hashlib.sha256((password + salt).encode()).hexdigest()
            return computed_hash == hash_value
        except ValueError:
            return False
    
    def _is_account_locked(self, username: str) -> bool:
        """Check if account is locked due to failed attempts"""
        if username not in self.failed_attempts:
            return False
        
        attempts, last_attempt_time = self.failed_attempts[username]
        
        # Reset if lockout duration has passed
        if datetime.now() - last_attempt_time > self.lockout_duration:
            del self.failed_attempts[username]
            return False
        
        return attempts >= self.max_attempts
    
    def _record_failed_attempt(self, username: str):
        """Record a failed login attempt"""
        if username not in self.failed_attempts:
            self.failed_attempts[username] = (0, datetime.now())
        
        attempts, _ = self.failed_attempts[username]
        self.failed_attempts[username] = (attempts + 1, datetime.now())
        
        logger.warning(f"Failed login attempt for user: {username}, attempts: {attempts + 1}")
    
    def _clear_failed_attempts(self, username: str):
        """Clear failed login attempts after successful login"""
        if username in self.failed_attempts:
            del self.failed_attempts[username]
    
    async def authenticate(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate user and return session token"""
        
        # Check if account is locked
        if self._is_account_locked(username):
            raise AuthenticationError(f"Account {username} is locked due to too many failed attempts")
        
        # Check if user exists
        if username not in self.users:
            self._record_failed_attempt(username)
            raise AuthenticationError("Invalid username or password")
        
        user = self.users[username]
        
        # Check if user is active
        if not user.get("active", True):
            raise AuthenticationError("Account is disabled")
        
        # Verify password
        if not self._verify_password(password, user["password_hash"]):
            self._record_failed_attempt(username)
            raise AuthenticationError("Invalid username or password")
        
        # Clear failed attempts
        self._clear_failed_attempts(username)
        
        # Update last login
        user["last_login"] = datetime.now()
        
        # Create session token
        session_id = secrets.token_urlsafe(32)
        session_data = {
            "username": username,
            "role": user["role"],
            "permissions": user["permissions"],
            "created_at": datetime.now(),
            "last_activity": datetime.now()
        }
        
        # Store session
        self.sessions[session_id] = session_data
        
        # Create JWT token
        token_payload = {
            "session_id": session_id,
            "username": username,
            "role": user["role"],
            "permissions": user["permissions"],
            "exp": datetime.utcnow() + self.token_expiry,
            "iat": datetime.utcnow()
        }
        
        token = jwt.encode(token_payload, self.secret_key, algorithm="HS256")
        
        # Create refresh token (longer-lived, only contains session reference)
        refresh_payload = {
            "session_id": session_id,
            "username": username,
            "type": "refresh",
            "exp": datetime.utcnow() + self.refresh_expiry,
            "iat": datetime.utcnow(),
        }
        refresh_token = jwt.encode(refresh_payload, self.secret_key, algorithm="HS256")
        
        logger.info(f"User {username} authenticated successfully")
        
        return {
            "token": token,
            "refresh_token": refresh_token,
            "session_id": session_id,
            "expires_in": int(self.token_expiry.total_seconds()),
            "user": {
                "username": username,
                "role": user["role"],
                "permissions": user["permissions"]
            }
        }
    
    async def validate_token(self, token: str) -> Dict[str, Any]:
        """Validate JWT token and return user info"""
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=["HS256"])
            session_id = payload.get("session_id")
            
            if not session_id or session_id not in self.sessions:
                raise AuthenticationError("Invalid session")
            
            session = self.sessions[session_id]
            
            # Check if session has expired
            if datetime.now() - session["created_at"] > self.token_expiry:
                del self.sessions[session_id]
                raise AuthenticationError("Session expired")
            
            # Update last activity
            session["last_activity"] = datetime.now()
            
            return {
                "username": session["username"],
                "role": session["role"],
                "permissions": session["permissions"],
                "session_id": session_id
            }
            
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid token")
    
    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """Issue a new access token using a valid refresh token."""
        try:
            payload = jwt.decode(refresh_token, self.secret_key, algorithms=["HS256"])
            if payload.get("type") != "refresh":
                raise AuthenticationError("Not a refresh token")
            session_id = payload.get("session_id")
            if not session_id or session_id not in self.sessions:
                raise AuthenticationError("Session expired — please log in again")
            session = self.sessions[session_id]
            # Issue new short-lived access token
            new_payload = {
                "session_id": session_id,
                "username": session["username"],
                "role": session["role"],
                "permissions": session["permissions"],
                "exp": datetime.utcnow() + self.token_expiry,
                "iat": datetime.utcnow(),
            }
            new_token = jwt.encode(new_payload, self.secret_key, algorithm="HS256")
            session["last_activity"] = datetime.now()
            return {"token": new_token, "expires_in": int(self.token_expiry.total_seconds())}
        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Refresh token expired — please log in again")
        except jwt.InvalidTokenError:
            raise AuthenticationError("Invalid refresh token")
    
    async def authorize(self, user_info: Dict[str, Any], required_permission: str) -> bool:
        """Check if user has required permission"""
        user_permissions = user_info.get("permissions", [])
        
        if required_permission not in user_permissions:
            logger.warning(f"Authorization failed for user {user_info.get('username')}: missing permission {required_permission}")
            return False
        
        return True
    
    async def logout(self, session_id: str) -> bool:
        """Logout user and invalidate session"""
        if session_id in self.sessions:
            username = self.sessions[session_id]["username"]
            del self.sessions[session_id]
            logger.info(f"User {username} logged out")
            return True
        return False
    
    async def change_password(self, username: str, old_password: str, new_password: str) -> bool:
        """Change user password"""
        if username not in self.users:
            raise AuthenticationError("User not found")
        
        user = self.users[username]
        
        # Verify old password
        if not self._verify_password(old_password, user["password_hash"]):
            raise AuthenticationError("Invalid current password")
        
        # Update password
        user["password_hash"] = self._hash_password(new_password)
        logger.info(f"Password changed for user {username}")
        
        return True
    
    async def create_user(self, username: str, password: str, role: str, permissions: List[str]) -> Dict[str, Any]:
        """Create a new user (admin only)"""
        if username in self.users:
            raise AuthenticationError("User already exists")
        
        # Validate role and permissions
        valid_roles = ["admin", "operator", "viewer"]
        if role not in valid_roles:
            raise AuthenticationError(f"Invalid role. Must be one of: {valid_roles}")
        
        valid_permissions = ["read_only", "diagnostic", "full_control"]
        for perm in permissions:
            if perm not in valid_permissions:
                raise AuthenticationError(f"Invalid permission: {perm}")
        
        # Create user
        self.users[username] = {
            "password_hash": self._hash_password(password),
            "role": role,
            "permissions": permissions,
            "created_at": datetime.now(),
            "last_login": None,
            "active": True
        }
        
        logger.info(f"User {username} created with role {role}")
        
        return {
            "username": username,
            "role": role,
            "permissions": permissions,
            "created_at": self.users[username]["created_at"]
        }
    
    async def deactivate_user(self, username: str) -> bool:
        """Deactivate a user account"""
        if username not in self.users:
            raise AuthenticationError("User not found")
        
        self.users[username]["active"] = False
        
        # Remove all active sessions for this user
        sessions_to_remove = [
            session_id for session_id, session in self.sessions.items()
            if session["username"] == username
        ]
        
        for session_id in sessions_to_remove:
            del self.sessions[session_id]
        
        logger.info(f"User {username} deactivated")
        return True
    
    def encrypt_sensitive_data(self, data: str) -> str:
        """Encrypt sensitive data"""
        return self.cipher.encrypt(data.encode()).decode()
    
    def decrypt_sensitive_data(self, encrypted_data: str) -> str:
        """Decrypt sensitive data"""
        return self.cipher.decrypt(encrypted_data.encode()).decode()
    
    def get_active_sessions(self) -> List[Dict[str, Any]]:
        """Get list of active sessions (admin only)"""
        return [
            {
                "session_id": session_id,
                "username": session["username"],
                "role": session["role"],
                "created_at": session["created_at"],
                "last_activity": session["last_activity"]
            }
            for session_id, session in self.sessions.items()
        ]
    
    def cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        current_time = datetime.now()
        expired_sessions = [
            session_id for session_id, session in self.sessions.items()
            if current_time - session["created_at"] > self.token_expiry
        ]
        
        for session_id in expired_sessions:
            username = self.sessions[session_id]["username"]
            del self.sessions[session_id]
            logger.info(f"Expired session removed for user {username}")
        
        # Clean up failed attempts
        expired_attempts = [
            username for username, (attempts, last_attempt) in self.failed_attempts.items()
            if current_time - last_attempt > self.lockout_duration
        ]
        
        for username in expired_attempts:
            del self.failed_attempts[username]
