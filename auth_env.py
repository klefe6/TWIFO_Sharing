"""
Single source-of-truth for OpenAI authentication.
Purpose: Load credentials with clear precedence and prevent silent overrides.
Author: Kevin Lefebvre
Last Updated: 2026-01-26
"""

import os
from pathlib import Path


def get_openai_api_key() -> str:
    """
    Load OpenAI API key with clear precedence:
    1. .env file in repo root (if present and contains non-empty OPENAI_API_KEY)
    2. os.environ['OPENAI_API_KEY'] (if set and non-empty)
    3. Raise clear error if neither found
    
    Returns:
        API key string
        
    Raises:
        SystemExit: If no valid key found
    """
    # Priority 1: .env file in repo root
    repo_root = Path(__file__).parent
    env_file = repo_root / ".env"
    
    if env_file.exists():
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('OPENAI_API_KEY='):
                        key = line.split('=', 1)[1].strip().strip('"').strip("'")
                        if key:
                            return key
        except Exception as e:
            print(f"[WARN] Failed to read .env file: {e}")
    
    # Priority 2: Environment variable
    key = os.environ.get('OPENAI_API_KEY', '').strip()
    if key:
        return key
    
    # Priority 3: Raise clear error
    print("[ERROR] OPENAI_API_KEY not found.")
    print("        Set it in .env file or environment variable.")
    print("        .env file location: " + str(env_file))
    raise SystemExit(1)


def describe_key(key: str) -> str:
    """
    Return safe description of API key (first 12 chars + "…") for logging.
    
    Args:
        key: Full API key
        
    Returns:
        Safe truncated string
    """
    if not key:
        return "<empty>"
    if len(key) < 12:
        return key[:4] + "…"
    return key[:12] + "…"


def assert_openai_auth_ok(model: str) -> None:
    """
    Verify OpenAI API key is valid by making a minimal API call.
    Exits immediately on authentication failure.
    
    Args:
        model: Model name to test with
        
    Raises:
        SystemExit: On authentication failure or API error
    """
    from openai_client import get_client
    from openai import AuthenticationError, BadRequestError
    
    try:
        client = get_client()
        key = os.environ.get('OPENAI_API_KEY', '')
        prefix = describe_key(key) if key else "<none>"
        base_url = client.base_url if hasattr(client, 'base_url') else "default"
        
        print(f"[DEBUG] Preflight check: model={model}, key_prefix={prefix}, base_url={base_url}")
        
        # Make minimal API call using same client as summarize
        response = client.responses.create(
            model=model,
            input=[{"role": "user", "content": "ping"}],
            max_output_tokens=64,  # minimum-safe value
        )
        
        # Success
        print(f"[DEBUG] Preflight passed: response received")
        return
        
    except AuthenticationError as e:
        # 401 Unauthorized - invalid/revoked key
        prefix = describe_key(key) if key else "<none>"
        print(f"[ERROR] OPENAI_API_KEY is invalid/revoked (401 Unauthorized).")
        print(f"        Current prefix={prefix}")
        print(f"        Error: {e}")
        print(f"        Fix env var before running.")
        raise SystemExit(1)
        
    except BadRequestError as e:
        # 400 Bad Request - treat as FAIL, not OK
        print(f"[ERROR] OpenAI API preflight FAILED (400 Bad Request).")
        print(f"        Model: {model}")
        print(f"        Error: {e}")
        print(f"        Full error payload: {e.response.json() if hasattr(e, 'response') else 'N/A'}")
        print(f"        This is NOT an auth success - fix the issue before running.")
        raise SystemExit(1)
        
    except SystemExit:
        raise
        
    except Exception as e:
        print(f"[ERROR] OpenAI API preflight failed: {type(e).__name__}: {e}")
        raise SystemExit(1)
