"""
Per-Session Connection Manager for Medi-AI-tor

Enables multiple technicians to connect to different servers simultaneously.
Each authenticated session gets its own DellAIAgent + AgentBrain instance.
Customer (unauthenticated) chat uses a shared default connection.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Any

logger = logging.getLogger(__name__)


class SessionConnection:
    """Holds a per-session agent + brain pair."""
    __slots__ = ('agent', 'brain', 'session_id', 'username', 'host',
                 'created_at', 'last_activity')

    def __init__(self, agent, brain, session_id: str, username: str):
        self.agent = agent
        self.brain = brain
        self.session_id = session_id
        self.username = username
        self.host = None
        self.created_at = datetime.now()
        self.last_activity = datetime.now()

    def touch(self):
        self.last_activity = datetime.now()


class SessionConnectionManager:
    """Manage per-session server connections.

    Each authenticated user gets their own DellAIAgent so that
    connecting to Server-A on session-1 does NOT affect session-2
    which is connected to Server-B.

    The 'default' key holds the shared connection used by the
    unauthenticated customer chat page.
    """

    def __init__(self, config, max_sessions: int = 100, idle_timeout_min: int = 60):
        self.config = config
        self.connections: Dict[str, SessionConnection] = {}
        self.max_sessions = max_sessions
        self.idle_timeout = timedelta(minutes=idle_timeout_min)
        self._lock = asyncio.Lock()

    async def get_or_create(self, session_id: str, username: str = "anonymous") -> SessionConnection:
        """Get existing connection or create a new one for this session."""
        async with self._lock:
            self._cleanup_idle()

            if session_id in self.connections:
                conn = self.connections[session_id]
                conn.touch()
                return conn

            # Enforce max sessions
            if len(self.connections) >= self.max_sessions:
                # Evict oldest idle session
                oldest = min(self.connections.values(), key=lambda c: c.last_activity)
                logger.info(f"Evicting idle session {oldest.session_id} (user={oldest.username}) to make room")
                await self._disconnect(oldest)
                del self.connections[oldest.session_id]

            # Create new agent + brain for this session
            from core.agent_core import DellAIAgent
            from core.agent_brain import AgentBrain
            agent = DellAIAgent(self.config)
            brain = AgentBrain(agent, self.config)

            conn = SessionConnection(agent, brain, session_id, username)
            self.connections[session_id] = conn
            logger.info(f"Created session connection for {username} (session={session_id[:8]}..., total={len(self.connections)})")
            return conn

    async def get_default(self) -> SessionConnection:
        """Get the shared default connection (for customer chat page)."""
        return await self.get_or_create("__default__", "customer")

    async def remove(self, session_id: str):
        """Disconnect and remove a session."""
        async with self._lock:
            conn = self.connections.pop(session_id, None)
            if conn:
                await self._disconnect(conn)
                logger.info(f"Removed session {session_id[:8]}... (user={conn.username})")

    async def _disconnect(self, conn: SessionConnection):
        """Safely disconnect an agent."""
        try:
            if conn.agent and conn.agent.is_connected():
                await conn.agent.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting session {conn.session_id[:8]}...: {e}")

    def _cleanup_idle(self):
        """Remove sessions that have been idle too long."""
        now = datetime.now()
        expired = [sid for sid, c in self.connections.items()
                   if sid != "__default__" and (now - c.last_activity) > self.idle_timeout]
        for sid in expired:
            conn = self.connections.pop(sid)
            logger.info(f"Expired idle session {sid[:8]}... (user={conn.username}, idle={now - conn.last_activity})")
            # Schedule disconnect in background (don't block)
            asyncio.create_task(self._disconnect(conn))

    def get_status(self) -> Dict[str, Any]:
        """Return status of all active sessions."""
        sessions = []
        for sid, conn in self.connections.items():
            sessions.append({
                "session_id": sid[:8] + "..." if len(sid) > 8 else sid,
                "username": conn.username,
                "host": conn.agent.current_session.server_host if conn.agent and conn.agent.current_session else None,
                "connected": conn.agent.is_connected() if conn.agent else False,
                "created_at": conn.created_at.isoformat(),
                "last_activity": conn.last_activity.isoformat(),
                "idle_seconds": int((datetime.now() - conn.last_activity).total_seconds()),
            })
        return {
            "total_sessions": len(self.connections),
            "max_sessions": self.max_sessions,
            "idle_timeout_min": int(self.idle_timeout.total_seconds() / 60),
            "sessions": sessions,
        }

    async def shutdown(self):
        """Disconnect all sessions (called on app shutdown)."""
        for sid, conn in list(self.connections.items()):
            await self._disconnect(conn)
        self.connections.clear()
        logger.info("All session connections closed")
