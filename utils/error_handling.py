"""
Robust Error Handling and Retry Logic for Dell Server AI Agent
"""

import asyncio
import logging
import time
import random
from typing import Dict, Any, Optional, Callable, TypeVar, Union
from functools import wraps
from datetime import datetime, timedelta
from enum import Enum
import json

logger = logging.getLogger(__name__)

T = TypeVar('T')

class ErrorType(str, Enum):
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    AUTHENTICATION_ERROR = "authentication_error"
    PERMISSION_ERROR = "permission_error"
    VALIDATION_ERROR = "validation_error"
    SERVER_ERROR = "server_error"
    UNKNOWN_ERROR = "unknown_error"

class ErrorSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class RetryStrategy(str, Enum):
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_INTERVAL = "fixed_interval"
    NO_RETRY = "no_retry"

class AgentError(Exception):
    """Base exception for Dell Server AI Agent"""
    
    def __init__(self, message: str, error_type: ErrorType = ErrorType.UNKNOWN_ERROR, 
                 severity: ErrorSeverity = ErrorSeverity.MEDIUM, 
                 context: Optional[Dict[str, Any]] = None,
                 original_error: Optional[Exception] = None):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.severity = severity
        self.context = context or {}
        self.original_error = original_error
        self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary for logging"""
        return {
            "message": self.message,
            "error_type": self.error_type,
            "severity": self.severity,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
            "original_error": str(self.original_error) if self.original_error else None
        }

class NetworkError(AgentError):
    """Network-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.NETWORK_ERROR, ErrorSeverity.MEDIUM, 
                        context, original_error)

class TimeoutError(AgentError):
    """Timeout-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.TIMEOUT_ERROR, ErrorSeverity.HIGH, 
                        context, original_error)

class AuthenticationError(AgentError):
    """Authentication-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.AUTHENTICATION_ERROR, ErrorSeverity.HIGH, 
                        context, original_error)

class PermissionError(AgentError):
    """Permission-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.PERMISSION_ERROR, ErrorSeverity.MEDIUM, 
                        context, original_error)

class ValidationError(AgentError):
    """Validation-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.VALIDATION_ERROR, ErrorSeverity.LOW, 
                        context, original_error)

class ServerError(AgentError):
    """Server-related errors"""
    
    def __init__(self, message: str, context: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message, ErrorType.SERVER_ERROR, ErrorSeverity.HIGH, 
                        context, original_error)

class RetryConfig:
    """Configuration for retry logic"""
    
    def __init__(self, 
                 max_attempts: int = 3,
                 base_delay: float = 1.0,
                 max_delay: float = 60.0,
                 backoff_multiplier: float = 2.0,
                 jitter: bool = True,
                 retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
                 retry_on_exceptions: Optional[List[Type[Exception]]] = None):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.jitter = jitter
        self.retry_strategy = retry_strategy
        self.retry_on_exceptions = retry_on_exceptions or [
            NetworkError, TimeoutError, ServerError
        ]
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """Determine if an exception should be retried"""
        if attempt >= self.max_attempts:
            return False
        
        # Check if exception type is in retry list
        for retry_exception in self.retry_on_exceptions:
            if isinstance(exception, retry_exception):
                return True
        
        # Check if it's a network-related exception
        if self._is_network_exception(exception):
            return True
        
        return False
    
    def _is_network_exception(self, exception: Exception) -> bool:
        """Check if exception is network-related"""
        network_indicators = [
            "connection", "timeout", "network", "dns", "socket", 
            "http", "ssl", "certificate", "unreachable"
        ]
        
        exception_str = str(exception).lower()
        return any(indicator in exception_str for indicator in network_indicators)
    
    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt"""
        if self.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay * (self.backoff_multiplier ** (attempt - 1))
        elif self.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.base_delay * attempt
        elif self.retry_strategy == RetryStrategy.FIXED_INTERVAL:
            delay = self.base_delay
        else:
            delay = self.base_delay
        
        # Apply maximum delay limit
        delay = min(delay, self.max_delay)
        
        # Add jitter to prevent thundering herd
        if self.jitter:
            jitter_amount = delay * 0.1  # 10% jitter
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0, delay)

class ErrorLogger:
    """Enhanced error logging with context and tracking"""
    
    def __init__(self, log_file: Optional[str] = None):
        self.log_file = log_file
        self.error_counts: Dict[str, int] = {}
        self.error_history: List[Dict[str, Any]] = []
        self.max_history_size = 1000
    
    def log_error(self, error: AgentError, context: Optional[Dict[str, Any]] = None):
        """Log error with full context"""
        error_context = error.context.copy()
        if context:
            error_context.update(context)
        
        # Update error counts
        error_key = f"{error.error_type}:{error.message[:50]}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
        
        # Add to history
        error_entry = {
            "error": error.to_dict(),
            "additional_context": error_context,
            "logged_at": datetime.now().isoformat()
        }
        
        self.error_history.append(error_entry)
        
        # Maintain history size
        if len(self.error_history) > self.max_history_size:
            self.error_history = self.error_history[-self.max_history_size:]
        
        # Log based on severity
        log_message = f"[{error.error_type.upper()}] {error.message}"
        if error.context:
            log_message += f" | Context: {json.dumps(error.context, default=str)}"
        
        if error.original_error:
            log_message += f" | Original: {str(error.original_error)}"
        
        if error.severity == ErrorSeverity.CRITICAL:
            logger.critical(log_message)
        elif error.severity == ErrorSeverity.HIGH:
            logger.error(log_message)
        elif error.severity == ErrorSeverity.MEDIUM:
            logger.warning(log_message)
        else:
            logger.info(log_message)
        
        # Write to file if configured
        if self.log_file:
            self._write_to_file(error_entry)
    
    def _write_to_file(self, error_entry: Dict[str, Any]):
        """Write error entry to file"""
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(error_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write error to file: {str(e)}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get error statistics"""
        total_errors = sum(self.error_counts.values())
        
        # Most common errors
        sorted_errors = sorted(self.error_counts.items(), key=lambda x: x[1], reverse=True)
        
        # Error distribution by type
        error_type_counts = {}
        for error_key, count in self.error_counts.items():
            error_type = error_key.split(":")[0]
            error_type_counts[error_type] = error_type_counts.get(error_type, 0) + count
        
        # Recent errors (last 24 hours)
        cutoff_time = datetime.now() - timedelta(hours=24)
        recent_errors = [
            entry for entry in self.error_history
            if datetime.fromisoformat(entry["logged_at"]) >= cutoff_time
        ]
        
        return {
            "total_errors": total_errors,
            "most_common_errors": sorted_errors[:10],
            "error_type_distribution": error_type_counts,
            "recent_errors_24h": len(recent_errors),
            "error_rate_per_hour": len(recent_errors) / 24.0 if recent_errors else 0
        }

def retry_on_failure(retry_config: Optional[RetryConfig] = None, 
                   fallback_value: Optional[T] = None):
    """Decorator for retry logic with fallback"""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            config = retry_config or RetryConfig()
            last_exception = None
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry
                    if not config.should_retry(e, attempt):
                        break
                    
                    # Log retry attempt
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}. Retrying...")
                    
                    # Calculate delay and wait
                    delay = config.calculate_delay(attempt)
                    await asyncio.sleep(delay)
            
            # All retries failed, handle fallback or raise
            if fallback_value is not None:
                logger.error(f"All retries failed for {func.__name__}. Using fallback value.")
                return fallback_value
            else:
                # Convert to appropriate AgentError
                if isinstance(last_exception, AgentError):
                    raise last_exception
                elif "timeout" in str(last_exception).lower():
                    raise TimeoutError(str(last_exception), original_error=last_exception)
                elif "connection" in str(last_exception).lower() or "network" in str(last_exception).lower():
                    raise NetworkError(str(last_exception), original_error=last_exception)
                else:
                    raise ServerError(str(last_exception), original_error=last_exception)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            config = retry_config or RetryConfig()
            last_exception = None
            
            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    # Check if we should retry
                    if not config.should_retry(e, attempt):
                        break
                    
                    # Log retry attempt
                    logger.warning(f"Attempt {attempt} failed for {func.__name__}: {str(e)}. Retrying...")
                    
                    # Calculate delay and wait
                    delay = config.calculate_delay(attempt)
                    time.sleep(delay)
            
            # All retries failed, handle fallback or raise
            if fallback_value is not None:
                logger.error(f"All retries failed for {func.__name__}. Using fallback value.")
                return fallback_value
            else:
                # Convert to appropriate AgentError
                if isinstance(last_exception, AgentError):
                    raise last_exception
                elif "timeout" in str(last_exception).lower():
                    raise TimeoutError(str(last_exception), original_error=last_exception)
                elif "connection" in str(last_exception).lower() or "network" in str(last_exception).lower():
                    raise NetworkError(str(last_exception), original_error=last_exception)
                else:
                    raise ServerError(str(last_exception), original_error=last_exception)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

def handle_errors(error_logger: Optional[ErrorLogger] = None, 
                   reraise: bool = True,
                   fallback_value: Optional[T] = None):
    """Decorator for comprehensive error handling"""
    def decorator(func: Callable[..., T]) -> Callable[..., Union[T, None]]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                # Convert to AgentError if needed
                if not isinstance(e, AgentError):
                    if "timeout" in str(e).lower():
                        error = TimeoutError(f"Timeout in {func.__name__}: {str(e)}", original_error=e)
                    elif "connection" in str(e).lower() or "network" in str(e).lower():
                        error = NetworkError(f"Network error in {func.__name__}: {str(e)}", original_error=e)
                    elif "permission" in str(e).lower() or "unauthorized" in str(e).lower():
                        error = PermissionError(f"Permission error in {func.__name__}: {str(e)}", original_error=e)
                    else:
                        error = ServerError(f"Error in {func.__name__}: {str(e)}", original_error=e)
                else:
                    error = e
                
                # Log the error
                if error_logger:
                    error_logger.log_error(error, {"function": func.__name__, "args": str(args), "kwargs": str(kwargs)})
                else:
                    logger.error(f"Error in {func.__name__}: {str(e)}")
                
                if reraise:
                    raise error
                elif fallback_value is not None:
                    return fallback_value
                else:
                    return None
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                # Convert to AgentError if needed
                if not isinstance(e, AgentError):
                    if "timeout" in str(e).lower():
                        error = TimeoutError(f"Timeout in {func.__name__}: {str(e)}", original_error=e)
                    elif "connection" in str(e).lower() or "network" in str(e).lower():
                        error = NetworkError(f"Network error in {func.__name__}: {str(e)}", original_error=e)
                    elif "permission" in str(e).lower() or "unauthorized" in str(e).lower():
                        error = PermissionError(f"Permission error in {func.__name__}: {str(e)}", original_error=e)
                    else:
                        error = ServerError(f"Error in {func.__name__}: {str(e)}", original_error=e)
                else:
                    error = e
                
                # Log the error
                if error_logger:
                    error_logger.log_error(error, {"function": func.__name__, "args": str(args), "kwargs": str(kwargs)})
                else:
                    logger.error(f"Error in {func.__name__}: {str(e)}")
                
                if reraise:
                    raise error
                elif fallback_value is not None:
                    return fallback_value
                else:
                    return None
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

class CircuitBreaker:
    """Circuit breaker pattern for preventing cascade failures"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60, 
                 expected_exception: Type[Exception] = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def __call__(self, func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise AgentError("Circuit breaker is OPEN", ErrorType.SERVER_ERROR, ErrorSeverity.HIGH)
            
            try:
                result = await func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise
            except Exception as e:
                # Don't track unexpected exceptions
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if self.state == "OPEN":
                if self._should_attempt_reset():
                    self.state = "HALF_OPEN"
                else:
                    raise AgentError("Circuit breaker is OPEN", ErrorType.SERVER_ERROR, ErrorSeverity.HIGH)
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except self.expected_exception as e:
                self._on_failure()
                raise
            except Exception as e:
                # Don't track unexpected exceptions
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    def _should_attempt_reset(self) -> bool:
        """Check if circuit breaker should attempt reset"""
        return (self.last_failure_time and 
                time.time() - self.last_failure_time >= self.recovery_timeout)
    
    def _on_success(self):
        """Handle successful operation"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """Handle failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"

# Global error logger instance
global_error_logger = ErrorLogger()

# Common retry configurations
NETWORK_RETRY_CONFIG = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    max_delay=30.0,
    backoff_multiplier=2.0,
    jitter=True,
    retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF
)

QUICK_RETRY_CONFIG = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=5.0,
    backoff_multiplier=1.5,
    jitter=True,
    retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF
)

LONG_RETRY_CONFIG = RetryConfig(
    max_attempts=7,
    base_delay=2.0,
    max_delay=120.0,
    backoff_multiplier=2.0,
    jitter=True,
    retry_strategy=RetryStrategy.EXPONENTIAL_BACKOFF
)

# Circuit breaker instances
API_CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
DATABASE_CIRCUIT_BREAKER = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
