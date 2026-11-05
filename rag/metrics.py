"""Activity numbers for the admin dashboard: how many messages per day, how fast, which files were used.

Stored in metrics/metrics.db (SQLite, standard library only; change the folder with METRICS_DIR, switch off
with METRICS=off). Only counts and times are stored, per day. Never a question, an answer, a name, a contact
detail, a chat id or a phone number, so this file holds no personal data. Knowledge-base file names are stored
(they are your own file names). Days older than 400 are deleted.

A disk problem never breaks the chat: failures go to stderr and the number is simply not counted.
"""
import os
import sqlite3
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEEP_DAYS = 400
BUCKET_SECONDS = 0.5      # answer-time histogram resolution
MAX_BUCKET = 120          # 60 seconds and slower share the last bucket
GAP_KINDS = ("no_match", "pending", "unanswered")


def enabled():
    return os.environ.get("METRICS", "on").strip().lower() not in ("off", "0", "false", "no")


def default_path():
    return Path(os.environ.get("METRICS_DIR", ROOT / "metrics")) / "metrics.db"


def open_default():
    if not enabled():
        return None
    try:
        return MetricsStore(default_path())
    except (sqlite3.Error, OSError) as e:
        print(f"[metrics] switched off, cannot open {default_path()}: {type(e).__name__}: {e}", file=sys.stderr)
        return None


def day_of(now):
    return time.strftime("%Y-%m-%d", time.localtime(now))


def days_back(n, now):
    """The last n calendar days, oldest first, ending today."""
    return [day_of(now - 86400 * i) for i in range(n - 1, -1, -1)]


class MetricsStore:
    def __init__(self, path):
        self.path, self.lock, self.last_purge = Path(path), threading.Lock(), 0.0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(self.path), check_same_thread=False, timeout=5)
        with self.lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript("""
                CREATE TABLE IF NOT EXISTS daily (day TEXT, channel TEXT, messages INTEGER DEFAULT 0, errors INTEGER DEFAULT 0,
                    gap_no_match INTEGER DEFAULT 0, gap_pending INTEGER DEFAULT 0, gap_unanswered INTEGER DEFAULT 0,
                    lat_n INTEGER DEFAULT 0, lat_sum REAL DEFAULT 0, PRIMARY KEY (day, channel));
                CREATE TABLE IF NOT EXISTS latency (day TEXT, bucket INTEGER, n INTEGER DEFAULT 0, PRIMARY KEY (day, bucket));
                CREATE TABLE IF NOT EXISTS files (day TEXT, file TEXT, n INTEGER DEFAULT 0, PRIMARY KEY (day, file));
            """)
            self.db.commit()

    def _run(self, fn, default=None):
        try:
            with self.lock:
                result = fn(self.db)
                self.db.commit()
                return result
        except (sqlite3.Error, OSError) as e:
            print(f"[metrics] {type(e).__name__}: {e}", file=sys.stderr)
            return default

    def record(self, channel, seconds, gap="", sources=(), error=False, now=None):
        """Count one answered (or failed) message."""
        now = time.time() if now is None else now
        day = day_of(now)
        channel = channel if channel in ("web", "whatsapp") else "other"
        gap_col = f"gap_{gap}" if gap in GAP_KINDS else None
        seconds = max(0.0, float(seconds))
        bucket = min(int(seconds / BUCKET_SECONDS), MAX_BUCKET)

        def op(db):
            db.execute("INSERT OR IGNORE INTO daily(day, channel) VALUES (?,?)", (day, channel))
            db.execute("UPDATE daily SET messages = messages + 1, errors = errors + ?, lat_n = lat_n + 1, "
                       "lat_sum = lat_sum + ? WHERE day=? AND channel=?", (1 if error else 0, seconds, day, channel))
            if gap_col:
                db.execute(f"UPDATE daily SET {gap_col} = {gap_col} + 1 WHERE day=? AND channel=?", (day, channel))
            db.execute("INSERT OR IGNORE INTO latency(day, bucket) VALUES (?,?)", (day, bucket))
            db.execute("UPDATE latency SET n = n + 1 WHERE day=? AND bucket=?", (day, bucket))
            for f in {str(s)[:120] for s in list(sources)[:10]}:
                db.execute("INSERT OR IGNORE INTO files(day, file) VALUES (?,?)", (day, f))
                db.execute("UPDATE files SET n = n + 1 WHERE day=? AND file=?", (day, f))
            if now - self.last_purge > 3600:
                self.last_purge = now
                cutoff = day_of(now - 86400 * KEEP_DAYS)
                for table in ("daily", "latency", "files"):
                    db.execute(f"DELETE FROM {table} WHERE day < ?", (cutoff,))
        self._run(op)

    def report(self, days, now=None):
        """Numbers for the last `days` days: per-day series (zeros filled in), answer-time percentiles, file usage."""
        now = time.time() if now is None else now
        window = days_back(days, now)
        first = window[0]

        def op(db):
            per_day = {d: {"messages": 0, "errors": 0, "web": 0, "whatsapp": 0, "gaps": 0} for d in window}
            lat_n = lat_sum = 0
            for day, channel, m, e, g1, g2, g3, ln, ls in db.execute(
                    "SELECT day, channel, messages, errors, gap_no_match, gap_pending, gap_unanswered, lat_n, lat_sum "
                    "FROM daily WHERE day >= ?", (first,)):
                if day not in per_day:
                    continue
                row = per_day[day]
                row["messages"] += m
                row["errors"] += e
                row["gaps"] += g1 + g2 + g3
                if channel in ("web", "whatsapp"):
                    row[channel] += m
                lat_n += ln
                lat_sum += ls
            buckets = dict(db.execute("SELECT bucket, SUM(n) FROM latency WHERE day >= ? GROUP BY bucket", (first,)).fetchall())
            files = db.execute("SELECT file, SUM(n) FROM files WHERE day >= ? GROUP BY file ORDER BY 2 DESC", (first,)).fetchall()
            return per_day, lat_n, lat_sum, buckets, files
        got = self._run(op)
        if got is None:
            return None
        per_day, lat_n, lat_sum, buckets, files = got
        total = sum(buckets.values())

        def percentile(p):
            if not total:
                return None
            need, seen = p * total, 0
            for b in sorted(buckets):
                seen += buckets[b]
                if seen >= need:
                    return (b + 1) * BUCKET_SECONDS  # upper edge of the bucket
            return None
        return {
            "days": [{"day": d, **per_day[d]} for d in window],
            "messages": sum(v["messages"] for v in per_day.values()),
            "errors": sum(v["errors"] for v in per_day.values()),
            "mean_seconds": (lat_sum / lat_n) if lat_n else None,
            "median_seconds": percentile(0.5),
            "p90_seconds": percentile(0.9),
            "files": [(f, int(n)) for f, n in files],
        }

    def close(self):
        with self.lock:
            self.db.close()
