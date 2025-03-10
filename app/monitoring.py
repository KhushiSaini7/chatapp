
import logging
import time
import prometheus_client
from prometheus_client import Counter, Histogram, Gauge
import os
from functools import wraps

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set up Prometheus metrics
REQUEST_COUNT = Counter(
    'request_count', 'App Request Count',
    ['app_name', 'endpoint', 'method', 'status']
)

REQUEST_LATENCY = Histogram(
    'request_latency_seconds', 'Request latency',
    ['app_name', 'endpoint', 'method']
)

TOKEN_COUNT = Counter(
    'token_count', 'LLM Token Usage',
    ['app_name', 'model', 'type']  # type can be 'prompt' or 'completion'
)

ACTIVE_USERS = Gauge(
    'active_users', 'Number of Active Users',
    ['app_name']
)

ERROR_COUNT = Counter(
    'error_count', 'Error Count',
    ['app_name', 'error_type']
)

# Set up metrics endpoint for Prometheus to scrape
def start_metrics_server(port=8000):
    """Start Prometheus metrics server"""
    from prometheus_client import start_http_server
    start_http_server(port)
    logger.info(f"Metrics server started on port {port}")

# Decorator for endpoint monitoring
def monitor_endpoint(endpoint=None):
    """Decorator to monitor FastAPI endpoints"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            method = "POST"  # Determine method dynamically in real implementation
            endpoint_name = endpoint or func.__name__
            app_name = os.getenv("APP_NAME", "chatbot-api")
            
            # Record request
            start_time = time.time()
            
            try:
                # Execute the endpoint function
                result = await func(*args, **kwargs)
                
                # Record successful request
                REQUEST_COUNT.labels(
                    app_name=app_name,
                    endpoint=endpoint_name,
                    method=method,
                    status="success"
                ).inc()
                
                return result
            except Exception as e:
                # Record failed request
                REQUEST_COUNT.labels(
                    app_name=app_name,
                    endpoint=endpoint_name,
                    method=method,
                    status="error"
                ).inc()
                
                # Record error
                ERROR_COUNT.labels(
                    app_name=app_name,
                    error_type=type(e).__name__
                ).inc()
                
                # Re-raise the exception
                raise
            finally:
                # Record request latency
                latency = time.time() - start_time
                REQUEST_LATENCY.labels(
                    app_name=app_name,
                    endpoint=endpoint_name,
                    method=method
                ).observe(latency)
        
        return wrapper
    return decorator

# Function to record token usage
def record_token_usage(model: str, prompt_tokens: int, completion_tokens: int):
    """Record token usage for billing and monitoring"""
    app_name = os.getenv("APP_NAME", "chatbot-api")
    
    # Record prompt tokens
    TOKEN_COUNT.labels(app_name=app_name, model=model, type="prompt").inc(prompt_tokens)
    
    # Record completion tokens
    TOKEN_COUNT.labels(app_name=app_name, model=model, type="completion").inc(completion_tokens)
    
    # Log token usage
    logger.info(f"Token usage - Model: {model}, Prompt: {prompt_tokens}, Completion: {completion_tokens}")

# Function to update active users
def update_active_users(count: int):
    """Update the active users gauge"""
    app_name = os.getenv("APP_NAME", "chatbot-api")
    ACTIVE_USERS.labels(app_name=app_name).set(count)
