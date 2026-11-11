#!/usr/bin/env python3
"""Minimal signed client for the generic HTTP bridge.

Example:
    BRIDGE_SHARED_SECRET=... python examples/bridge_client.py \
        --user ada --text "!help"

Only the Python standard library is required, so this can run from any machine or
be translated directly into another language.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.request


def sign(secret: str, timestamp: str, body: bytes) -> str:
    signed = f"{timestamp}.".encode() + body
    return "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send one message to the GitHub Community Bot bridge"
    )
    parser.add_argument("--url", default="http://127.0.0.1:8080", help="bot base URL")
    parser.add_argument("--secret", default=os.getenv("BRIDGE_SHARED_SECRET", ""))
    parser.add_argument("--user", default="local-user", help="stable user ID from your chat app")
    parser.add_argument("--name", default="Local user")
    parser.add_argument("--channel", default="bridge-room")
    parser.add_argument("--locale", default=None, help="en, zh, ja (optional)")
    parser.add_argument("--text", default="!help")
    parser.add_argument("--dm", action="store_true", help="treat this as a direct message")
    parser.add_argument("--mentions-bot", action="store_true")
    args = parser.parse_args()

    if not args.secret:
        print("Set BRIDGE_SHARED_SECRET or pass --secret", file=sys.stderr)
        return 2

    payload = {
        "text": args.text,
        "user_id": args.user,
        "user_name": args.name,
        "channel_id": args.channel,
        "is_dm": args.dm,
        "mentions_bot": args.mentions_bot,
        "message_id": f"example-{int(time.time())}",
    }
    if args.locale:
        payload["locale"] = args.locale
    body = json.dumps(payload).encode()
    timestamp = str(int(time.time()))
    request = urllib.request.Request(
        f"{args.url.rstrip('/')}/api/v1/messages",
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Bridge-Timestamp": timestamp,
            "X-Bridge-Signature": sign(args.secret, timestamp, body),
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = json.loads(response.read())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read().decode(errors='replace')}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"Could not reach the bot: {exc.reason}", file=sys.stderr)
        return 1

    for reply in data.get("replies", []):
        print(reply.get("text", ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
