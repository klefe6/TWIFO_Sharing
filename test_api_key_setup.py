"""
Quick test to verify API key setup is working.
"""
from pathlib import Path
from test_summarize_one import load_api_key

print("="*60)
print("API KEY SETUP TEST")
print("="*60)

# Check .env file
env_file = Path(".env")
print(f"[1] .env file exists: {env_file.exists()}")

# Load API key
key = load_api_key()
print(f"[2] API Key loaded: {bool(key)}")

if key:
    print(f"[3] Key length: {len(key)} characters")
    print(f"[4] Key preview: {key[:20]}...")
    print("\n" + "="*60)
    print("RESULT: SUCCESS - Ready to use!")
    print("="*60)
else:
    print("\n" + "="*60)
    print("RESULT: FAILED - Check .env file or environment variables")
    print("="*60)
    print("\nTroubleshooting:")
    print("  1. Check if .env file exists in this directory")
    print("  2. Make sure it contains: OPENAI_API_KEY=your_key_here")
    print("  3. Or set Windows environment variable and restart PowerShell")
