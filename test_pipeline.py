#!/usr/bin/env python3
"""Manually run compliance-checker.pipe against RocketRide Cloud and send it text.

The bare `rocketride start` CLI command has a bug (it subscribes to events with
a null token before the pipeline exists, which confuses the server's
project/source resolution) so this talks to the SDK directly instead, which is
confirmed working.

Usage:
    # Start a fresh pipeline run and send one input, print the result, leave it running
    python3 test_pipeline.py "We are an EU company that never responds to deletion requests..."

    # Reuse an already-running pipeline (token printed by a previous run)
    python3 test_pipeline.py --token tk_xxxxxxxx "some other input"

    # No text given -> interactive loop, one input per line, Ctrl-D to quit
    python3 test_pipeline.py --token tk_xxxxxxxx

    # Terminate a running pipeline when you're done
    python3 test_pipeline.py --token tk_xxxxxxxx --stop

Requires ROCKETRIDE_URI and ROCKETRIDE_APIKEY in the environment (see .env).
"""

import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.venv/lib/python3.13/site-packages'))
from rocketride import RocketRideClient  # noqa: E402


def on_event(message):
    event = message.get('event')
    body = message.get('body', {})
    if event == 'apaevt_flow' and body.get('trace', {}).get('result') == 'error':
        print(f"  [pipeline error @ {body.get('component')}]: {body['trace'].get('error')}", file=sys.stderr)
    elif event == 'apaevt_status_error':
        print(f"  [status error]: {body}", file=sys.stderr)


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('text', nargs='?', help='Text to send. Omit for interactive mode.')
    parser.add_argument('--token', help='Reuse an existing running pipeline instead of starting a new one.')
    parser.add_argument('--pipeline', default='compliance-checker.pipe', help='Pipeline file to start.')
    parser.add_argument('--stop', action='store_true', help='Terminate the pipeline (requires --token) and exit.')
    args = parser.parse_args()

    uri = os.environ.get('ROCKETRIDE_URI')
    apikey = os.environ.get('ROCKETRIDE_APIKEY')
    if not uri or not apikey:
        sys.exit('Set ROCKETRIDE_URI and ROCKETRIDE_APIKEY in your environment (e.g. `set -a && source .env && set +a`).')

    client = RocketRideClient(uri, auth=apikey, on_event=on_event)
    await client.connect()

    try:
        if args.stop:
            if not args.token:
                sys.exit('--stop requires --token')
            await client.terminate(args.token)
            print(f'Terminated {args.token}')
            return

        token = args.token
        if not token:
            with open(args.pipeline) as f:
                pipeline = json.load(f)
            result = await client.use(pipeline=pipeline, threads=4, pipelineTraceLevel='full')
            token = result['token']
            print(f'Started pipeline. Token: {token}')
            print(f'(reuse with: python3 test_pipeline.py --token {token} "...")')
            await client.set_events(token=token, event_types=['ALL'])
            await asyncio.sleep(2)  # let the webhook server finish booting

        async def send_one(text: str):
            print(f'\n>>> Sending: {text[:80]}{"..." if len(text) > 80 else ""}')
            try:
                response = await asyncio.wait_for(
                    client.send(token, text, mimetype='text/plain'),
                    timeout=180,
                )
                print('=== RESULT ===')
                print(json.dumps(response, indent=2))
            except Exception as e:
                print(f'ERROR: {type(e).__name__}: {e}', file=sys.stderr)

        if args.text:
            await send_one(args.text)
        else:
            print('Interactive mode. Type text and press Enter to send (Ctrl-D to quit).')
            loop = asyncio.get_event_loop()
            while True:
                try:
                    line = await loop.run_in_executor(None, input, '\n> ')
                except EOFError:
                    break
                if line.strip():
                    await send_one(line)
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
