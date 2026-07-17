#!/usr/bin/env python3
import asyncio
import os
import sys
import glob

# Ensure we use packages from virtual environment
site_packages_dirs = glob.glob(os.path.join(os.path.dirname(__file__), '.venv/lib/python3.*/site-packages'))
if site_packages_dirs:
    sys.path.insert(0, site_packages_dirs[0])

try:
    from rocketride import RocketRideClient
except ImportError:
    sys.exit("Error: rocketride SDK is not installed. Run setup/pip install first.")

async def main():
    # Load .env manually if it exists
    if os.path.exists('.env'):
        with open('.env') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

    uri = os.environ.get('ROCKETRIDE_URI')
    apikey = os.environ.get('ROCKETRIDE_APIKEY')
    print(f"Connecting to RocketRide server at {uri}...")
    
    client = RocketRideClient(uri, auth=apikey)
    try:
        await client.connect()
        print("✓ Successfully connected to RocketRide server!")
        
        # Check active tasks
        tasks = await client.connect() # connect returns info or is_connected can be checked
        print("Connection status:", "Connected" if client.is_connected() else "Not connected")
        
        # Test OpenAI API key presence
        openai_key = os.environ.get('ROCKETRIDE_OPENAI_KEY')
        if openai_key:
            print("✓ ROCKETRIDE_OPENAI_KEY is configured.")
        else:
            print("⚠ ROCKETRIDE_OPENAI_KEY is NOT configured in .env. LLM nodes will fail until you provide a valid OpenAI API key.")
            
    except Exception as e:
        print(f"✗ Failed to connect: {e}")
        sys.exit(1)
    finally:
        await client.disconnect()

if __name__ == '__main__':
    asyncio.run(main())
