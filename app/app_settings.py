"""General app settings kept on the server (separate from the AI settings in llm.py).

Public address for phones (SRS FR-4.6a, D-21): the HTTPS address that phones can reach (e.g. the
Cloudflare tunnel). Every QR code uses it, so the lecturer's laptop can keep using `localhost` —
even on a network where the laptop itself cannot open the tunnel address.
"""
import sqlite3
from urllib.parse import urlparse

PUBLIC_URL_KEY = "public_url"


class AppSettings:
    def __init__(self, db: sqlite3.Connection):
        self.db = db

    def public_url(self) -> str:
        r = self.db.execute("SELECT value FROM settings WHERE key = ?", (PUBLIC_URL_KEY,)).fetchone()
        return r["value"] if r else ""

    def set_public_url(self, url: str) -> str:
        """Store just the origin (https://host). Empty clears it. Phones need HTTPS for the microphone."""
        url = (url or "").strip()
        if url:
            parsed = urlparse(url)
            if parsed.scheme != "https" or not parsed.netloc:
                raise ValueError("Use the https:// address that phones can open (e.g. the tunnel link)")
            url = f"https://{parsed.netloc}"
        self.db.execute("INSERT INTO settings(key, value) VALUES (?, ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (PUBLIC_URL_KEY, url))
        return url
