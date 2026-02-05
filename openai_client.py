"""
Single OpenAI client instance for consistent authentication.
Purpose: Prevent auth inconsistencies between preflight and summarize calls.
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import os
from openai import OpenAI
from auth_env import get_openai_api_key, describe_key


_client = None


def get_client() -> OpenAI:
    """
    Get singleton OpenAI client with consistent authentication.
    
    Returns:
        OpenAI client instance
        
    Note:
        - Loads key from auth_env.py (single source-of-truth)
        - Sets os.environ["OPENAI_API_KEY"] for consistency
        - Returns same client instance on subsequent calls
    """
    global _client
    
    if _client is None:
        # Load key from single source-of-truth
        api_key = get_openai_api_key()
        
        # Set in environment for any modules that might read it
        os.environ["OPENAI_API_KEY"] = api_key
        
        # Create client with explicit key (no env lookups)
        _client = OpenAI(api_key=api_key)
        
        # Debug logging
        prefix = describe_key(api_key)
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        print(f"[DEBUG] OpenAI client initialized: key_prefix={prefix}, base_url={base_url}")
    
    return _client
