"""Parse HTTP client timeouts from environment (connect, read) or a single value for both."""
import os


def parse_timeout_env(key, default_connect=3.0, default_read=10.0):
    """
    Env format: "3,10" (connect, read seconds) or single "8" for both.
    """
    raw = (os.getenv(key) or '').strip()
    if not raw:
        return (float(default_connect), float(default_read))
    if ',' in raw:
        parts = [p.strip() for p in raw.split(',', 1)]
        try:
            return (float(parts[0]), float(parts[1]))
        except (ValueError, IndexError):
            return (float(default_connect), float(default_read))
    try:
        v = float(raw)
        return (v, v)
    except ValueError:
        return (float(default_connect), float(default_read))
