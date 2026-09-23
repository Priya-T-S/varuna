"""Shared test setup: an isolated throwaway database and no background monitor
or real notification credentials, whatever the developer's .env contains."""

import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="varuna-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["ALERTS_ENABLED"] = "false"
for _key in (
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_DEFAULT_CHAT_ID", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD",
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_SMS_FROM", "TWILIO_WHATSAPP_FROM",
):
    os.environ[_key] = ""
