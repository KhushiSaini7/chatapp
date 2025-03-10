import os
import asyncio
from typing import List, Dict, Any, Optional
import openai
import tiktoken
import redis
import json
import logging
from tenacity import retry, stop_after_attempt, wait_exponential
# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Redis client for caching
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
redis_client = redis.from_url(REDIS_URL)

# Get API key from environment
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# Token limits for different models
MODEL_TOKEN_LIMITS = {
    "gpt-3.5-turbo": 4096,
    "gpt-4": 8192,
    "claude-2": 100000
}

def get_llm_client(model_name: str):
    """Return appropriate client based on model name"""
    if model_name.startswith("gpt"):
        return OpenAIClient(api_key=OPENAI_API_KEY, model_name=model_name)
    elif model_name.startswith("claude"):
        return AnthropicClient(api_key=ANTHROPIC_API_KEY, model_name=model_name)
    else:
        # Default to OpenAI
        return OpenAIClient(api_key=OPENAI_API_KEY, model_name="gpt-3.5-turbo")

class BaseLLMClient:
    """Base class for LLM clients"""
    def __init__(self, api_key: str, model_name: str):
        self.api_key = api_key
        self.model_name = model_name
    
    async def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate a response from the LLM"""
        raise NotImplementedError("Subclasses must implement this method")
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text"""
        raise NotImplementedError("Subclasses must implement this method")

class OpenAIClient(BaseLLMClient):
    """Client for OpenAI models"""
    def __init__(self, api_key: str, model_name: str = "gpt-3.5-turbo"):
        super().__init__(api_key, model_name)
        openai.api_key = api_key
        
        # Get encoding for token counting
        if model_name.startswith("gpt-3.5"):
            self.encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        elif model_name.startswith("gpt-4"):
            self.encoding = tiktoken.encoding_for_model("gpt-4")
        else:
            self.encoding = tiktoken.get_encoding("cl100k_base")
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate a response from the OpenAI model"""
        try:
            response = await openai.ChatCompletion.acreate(
                model=self.model_name,
                messages=messages,
                temperature=0.7,
                max_tokens=1000,
                top_p=1.0,
                frequency_penalty=0.0,
                presence_penalty=0.0
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"Error generating response from OpenAI: {str(e)}")
            raise
    
    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in the given text"""
        return len(self.encoding.encode(text))

class AnthropicClient(BaseLLMClient):
    """Client for Anthropic models"""
    def __init__(self, api_key: str, model_name: str = "claude-2"):
        super().__init__(api_key, model_name)
        # For Anthropic, we'd import their SDK here
        # This is a placeholder - actual implementation would use Anthropic's SDK
    
    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def generate_response(self, messages: List[Dict[str, str]]) -> str:
        """Generate a response from the Anthropic model"""
        try:
            # This is a placeholder - actual implementation would use Anthropic's API
            # Convert messages to Anthropic format
            prompt = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])
            prompt += "\nassistant:"
            
            # Call Anthropic API (placeholder)
            # response = anthropic.completion(prompt=prompt, model=self.model_name)
            # return response.completion
            
            # For now, return a placeholder
            return "This is a placeholder for Anthropic response. Implement actual API call here."
        except Exception as e:
            logger.error(f"Error generating response from Anthropic: {str(e)}")
            raise
    
    def count_tokens(self, text: str) -> int:
        """
        Approximate token counting for Anthropic models
        This is a rough approximation - actual implementation would use Anthropic's tokenizer
        """
        # Roughly 4 characters per token for English text
        return len(text) // 4

async def process_message(
    llm_client: BaseLLMClient,
    message_history: List[Dict[str, str]],
    current_message: str
) -> str:
    """Process a message through the LLM and return the response"""
    # Check cache first
    cache_key = f"response:{hash(json.dumps(message_history))}{hash(current_message)}"
    cached_response = redis_client.get(cache_key)
    
    if cached_response:
        return cached_response.decode('utf-8')
    
    # Prepare messages for LLM
    messages = message_history.copy()
    
    # Add system message if not present
    if not messages or messages[0]["role"] != "system":
        messages.insert(0, {
            "role": "system",
            "content": "You are a helpful, friendly AI assistant. Provide accurate, concise, and helpful responses."
        })
    
    # Add current message
    messages.append({"role": "user", "content": current_message})
    
    # Ensure we don't exceed token limit by truncating history if needed
    truncated_messages = truncate_messages(llm_client, messages)
    
    # Generate response
    response = await llm_client.generate_response(truncated_messages)
    
    # Cache the response (expire after 1 hour)
    redis_client.setex(cache_key, 3600, response)
    
    return response

def truncate_messages(llm_client: BaseLLMClient, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Truncate message history to fit within token limit"""
    # Get token limit for the model
    token_limit = MODEL_TOKEN_LIMITS.get(llm_client.model_name, 4096)
    
    # Reserve tokens for the response (1000) and system message
    available_tokens = token_limit - 1000
    
    # Always keep system message
    system_message = messages[0] if messages and messages[0]["role"] == "system" else None
    if system_message:
        system_tokens = llm_client.count_tokens(system_message["content"])
        available_tokens -= system_tokens
        messages = messages[1:]
    
    # Count tokens in messages
    message_tokens = []
    for msg in messages:
        tokens = llm_client.count_tokens(msg["content"])
        message_tokens.append(tokens)
    
    # Remove oldest messages until we're under the limit
    while sum(message_tokens) > available_tokens and len(message_tokens) > 1:
        message_tokens.pop(0)
        messages.pop(0)
    
    # Add system message back if it exists
    if system_message:
        messages.insert(0, system_message)
    
    return messages
