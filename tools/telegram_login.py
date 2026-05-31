import os
import sys

root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from app.config import config
from app.utils import utils


def main():
    try:
        from telethon.sync import TelegramClient
    except ImportError:
        print("Telethon is not installed. Run: pip install telethon==1.43.0")
        return 1

    api_id = config.app.get("telegram_api_id", "")
    api_hash = str(config.app.get("telegram_api_hash", "")).strip()
    if not api_id or not api_hash:
        print("Set telegram_api_id and telegram_api_hash in config.toml first.")
        return 1

    session_file = str(config.app.get("telegram_session_file", "")).strip()
    if not session_file:
        session_file = os.path.join(utils.storage_dir("telegram", create=True), "telethon_news")

    print(f"Creating Telegram session at: {session_file}.session")
    print("Use the throwaway Telegram account phone number when Telethon asks.")
    with TelegramClient(session_file, int(api_id), api_hash) as client:
        me = client.get_me()
        print(f"Logged in as: {getattr(me, 'username', '') or getattr(me, 'phone', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
