"""Prints your Telegram chat id.

1. Create a bot with @BotFather and copy the token.
2. Send any message to your bot (e.g. "oi").
3. Run:  python scripts/get_chat_id.py <TOKEN>
"""

import sys

import requests

if len(sys.argv) != 2:
    sys.exit("usage: python scripts/get_chat_id.py <TELEGRAM_BOT_TOKEN>")

resp = requests.get(f"https://api.telegram.org/bot{sys.argv[1]}/getUpdates", timeout=30)
resp.raise_for_status()
updates = resp.json().get("result", [])
chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "")
         for u in updates if "message" in u}

if not chats:
    sys.exit("No messages found. Send a message to your bot first, then run this again.")
for chat_id, name in chats.items():
    print(f"TELEGRAM_CHAT_ID = {chat_id}   ({name})")
