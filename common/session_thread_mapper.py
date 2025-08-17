"""
Session-Thread Mapper for A2A Agent System

This module provides a lightweight in-memory mapping between ADK session IDs 
and LangGraph thread IDs to ensure conversation continuity across agent interactions.
"""

import hashlib
from typing import Dict, Tuple, Optional
import threading


class SessionThreadMapper:
    """
    In-memory mapper that creates consistent thread IDs from session context.
    
    This ensures that the same user session always maps to the same LangGraph
    thread ID, enabling proper conversation continuity and memory persistence.
    """
    
    def __init__(self):
        self._session_to_thread: Dict[Tuple[str, str], str] = {}
        self._thread_to_session: Dict[str, Tuple[str, str]] = {}
        self._lock = threading.Lock()
    
    def get_thread_id(self, user_id: str, session_id: str) -> str:
        """
        Get or create a consistent thread ID for the given user and session.
        
        Args:
            user_id: The user identifier from ADK
            session_id: The session identifier from ADK
            
        Returns:
            A consistent thread ID for LangGraph agents
        """
        session_key = (user_id, session_id)
        
        with self._lock:
            if session_key in self._session_to_thread:
                return self._session_to_thread[session_key]
            
            # Create a deterministic thread ID based on user and session
            thread_id = self._generate_thread_id(user_id, session_id)
            
            # Store bidirectional mapping
            self._session_to_thread[session_key] = thread_id
            self._thread_to_session[thread_id] = session_key
            
            return thread_id
    
    def get_session_info(self, thread_id: str) -> Optional[Tuple[str, str]]:
        """
        Get session information from a thread ID.
        
        Args:
            thread_id: The LangGraph thread ID
            
        Returns:
            Tuple of (user_id, session_id) or None if not found
        """
        with self._lock:
            return self._thread_to_session.get(thread_id)
    
    def _generate_thread_id(self, user_id: str, session_id: str) -> str:
        """
        Generate a deterministic thread ID from user and session IDs.
        
        This ensures the same user/session combination always produces
        the same thread ID, enabling conversation continuity.
        """
        # Create a deterministic hash from user_id and session_id
        combined = f"{user_id}:{session_id}"
        hash_object = hashlib.sha256(combined.encode())
        # Use first 16 characters of hex digest for readability
        return f"thread_{hash_object.hexdigest()[:16]}"
    
    def clear_session(self, user_id: str, session_id: str) -> bool:
        """
        Clear a specific session mapping.
        
        Args:
            user_id: The user identifier
            session_id: The session identifier
            
        Returns:
            True if session was found and cleared, False otherwise
        """
        session_key = (user_id, session_id)
        
        with self._lock:
            if session_key in self._session_to_thread:
                thread_id = self._session_to_thread[session_key]
                del self._session_to_thread[session_key]
                del self._thread_to_session[thread_id]
                return True
            return False
    
    def get_active_sessions(self) -> Dict[Tuple[str, str], str]:
        """
        Get all active session mappings.
        
        Returns:
            Dictionary mapping (user_id, session_id) to thread_id
        """
        with self._lock:
            return self._session_to_thread.copy()
    
    def clear_all(self):
        """Clear all session mappings."""
        with self._lock:
            self._session_to_thread.clear()
            self._thread_to_session.clear()


# Global singleton instance for the application
_session_mapper_instance: Optional[SessionThreadMapper] = None
_instance_lock = threading.Lock()


def get_session_mapper() -> SessionThreadMapper:
    """
    Get the global SessionThreadMapper instance (singleton pattern).
    
    Returns:
        The global SessionThreadMapper instance
    """
    global _session_mapper_instance
    
    if _session_mapper_instance is None:
        with _instance_lock:
            if _session_mapper_instance is None:
                _session_mapper_instance = SessionThreadMapper()
    
    return _session_mapper_instance


def reset_session_mapper():
    """Reset the global session mapper (useful for testing)."""
    global _session_mapper_instance
    
    with _instance_lock:
        if _session_mapper_instance is not None:
            _session_mapper_instance.clear_all()
        _session_mapper_instance = None
