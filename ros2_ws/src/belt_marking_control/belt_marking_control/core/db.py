"""SQLite persistence: recipes, jobs, production log, alarm history, counters, users,
audit trail and cycle times (for anomaly detection). One file, WAL mode so the UI can read
while the control node writes."""

import csv
import datetime
import hashlib
import json
import os
import secrets
import sqlite3
import threading
from typing import Dict, Iterable, List, Optional

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS recipes (
    name TEXT PRIMARY KEY, spec TEXT NOT NULL, belt_width_mm REAL,
    updated TEXT NOT NULL, updated_by TEXT);
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, recipe TEXT, spec TEXT,
    started TEXT, ended TEXT, final_state TEXT, marks INTEGER DEFAULT 0,
    pieces INTEGER DEFAULT 0, rejects INTEGER DEFAULT 0, duration_s REAL DEFAULT 0,
    user TEXT, message TEXT);
CREATE TABLE IF NOT EXISTS production_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, job_id TEXT, event TEXT,
    label INTEGER, station INTEGER, belt_coord_mm REAL, length_mm REAL, detail TEXT);
CREATE TABLE IF NOT EXISTS alarm_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, code INTEGER, code_text TEXT,
    severity INTEGER, event TEXT, text TEXT, detail TEXT, user TEXT);
CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value REAL);
CREATE TABLE IF NOT EXISTS users (
    name TEXT PRIMARY KEY, role TEXT NOT NULL, pin_hash TEXT NOT NULL, salt TEXT NOT NULL,
    created TEXT, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, user TEXT, action TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS cycle_times (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, kind TEXT, seconds REAL);
CREATE INDEX IF NOT EXISTS idx_log_job ON production_log(job_id);
CREATE INDEX IF NOT EXISTS idx_cycle_kind ON cycle_times(kind, id);
"""

ROLES = ('operator', 'technician', 'admin')
ROLE_LEVEL = {r: i for i, r in enumerate(ROLES)}
DEFAULT_USERS = (('operator', 'operator', '1111'), ('technician', 'technician', '2222'),
                 ('admin', 'admin', '9999'))   # change at commissioning (ASSUMPTIONS A-64)


def utcnow() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='milliseconds')


def hash_pin(pin: str, salt: str) -> str:
    """PBKDF2 hash of a PIN (never stored in clear text)."""
    return hashlib.pbkdf2_hmac('sha256', pin.encode(), salt.encode(), 60000).hex()


class ProductionDb:
    """SQLite access for recipes, jobs, logs, alarms, users and audit."""

    def __init__(self, path: str, read_only: bool = False):
        path = os.path.expanduser(path)
        self.path = path
        if path != ':memory:':
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        uri = f'file:{path}?mode=ro' if read_only else path
        self.conn = sqlite3.connect(uri, uri=read_only, check_same_thread=False, timeout=5.0)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        if not read_only:
            with self.lock:
                if path != ':memory:':
                    self.conn.execute('PRAGMA journal_mode=WAL')
                self.conn.executescript(SCHEMA)
                self.conn.execute('INSERT OR IGNORE INTO meta VALUES (?, ?)',
                                  ('schema_version', str(SCHEMA_VERSION)))
                self.conn.commit()
                if not self.list_users():
                    for name, role, pin in DEFAULT_USERS:
                        self.add_user(name, role, pin)

    def _exec(self, sql: str, args: Iterable = ()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, tuple(args))
            self.conn.commit()
            return cur

    def _query(self, sql: str, args: Iterable = ()) -> List[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, tuple(args)).fetchall()]

    # ------------------------------------------------------------------ recipes
    def save_recipe(self, name: str, spec_json: str, belt_width_mm: float, user: str = '',
                    overwrite: bool = True) -> bool:
        exists = self._query('SELECT 1 FROM recipes WHERE name=?', (name,))
        if exists and not overwrite:
            return False
        self._exec('INSERT OR REPLACE INTO recipes VALUES (?,?,?,?,?)',
                   (name, spec_json, belt_width_mm, utcnow(), user))
        self.audit(user, 'recipe_save', name)
        return True

    def load_recipe(self, name: str) -> Optional[str]:
        rows = self._query('SELECT spec FROM recipes WHERE name=?', (name,))
        return rows[0]['spec'] if rows else None

    def list_recipes(self) -> List[dict]:
        return self._query('SELECT name, belt_width_mm, updated, updated_by FROM recipes '
                           'ORDER BY name')

    def delete_recipe(self, name: str, user: str = '') -> bool:
        cur = self._exec('DELETE FROM recipes WHERE name=?', (name,))
        if cur.rowcount:
            self.audit(user, 'recipe_delete', name)
        return cur.rowcount > 0

    # ------------------------------------------------------------------ jobs / log
    def job_started(self, job_id: str, recipe: str, spec_json: str, user: str = '') -> int:
        cur = self._exec('INSERT INTO jobs (job_id, recipe, spec, started, user) '
                         'VALUES (?,?,?,?,?)', (job_id, recipe, spec_json, utcnow(), user))
        return cur.lastrowid

    def job_ended(self, row_id: int, final_state: str, marks: int, pieces: int, rejects: int,
                  duration_s: float, message: str = '') -> None:
        self._exec('UPDATE jobs SET ended=?, final_state=?, marks=?, pieces=?, rejects=?, '
                   'duration_s=?, message=? WHERE id=?',
                   (utcnow(), final_state, marks, pieces, rejects, duration_s, message, row_id))

    def log_event(self, ev: Dict) -> None:
        self._exec('INSERT INTO production_log (ts, job_id, event, label, station, '
                   'belt_coord_mm, length_mm, detail) VALUES (?,?,?,?,?,?,?,?)',
                   (utcnow(), ev.get('job_id', ''), ev['type'], ev.get('label', 0),
                    ev.get('station', 0), ev.get('belt_coord_mm', 0.0),
                    ev.get('length_mm', 0.0), ev.get('detail', '')))

    def log_alarm(self, code: int, code_text: str, severity: int, event: str, text: str,
                  detail: str = '', user: str = '') -> None:
        self._exec('INSERT INTO alarm_history (ts, code, code_text, severity, event, text, '
                   'detail, user) VALUES (?,?,?,?,?,?,?,?)',
                   (utcnow(), code, code_text, severity, event, text, detail, user))

    def log_cycle(self, kind: str, seconds: float) -> None:
        self._exec('INSERT INTO cycle_times (ts, kind, seconds) VALUES (?,?,?)',
                   (utcnow(), kind, seconds))

    def jobs(self, limit: int = 200) -> List[dict]:
        return self._query('SELECT * FROM jobs ORDER BY id DESC LIMIT ?', (limit,))

    def alarm_history(self, limit: int = 500) -> List[dict]:
        return self._query('SELECT * FROM alarm_history ORDER BY id DESC LIMIT ?', (limit,))

    def production_log(self, job_id: Optional[str] = None, limit: int = 1000) -> List[dict]:
        if job_id:
            return self._query('SELECT * FROM production_log WHERE job_id=? ORDER BY id DESC '
                               'LIMIT ?', (job_id, limit))
        return self._query('SELECT * FROM production_log ORDER BY id DESC LIMIT ?', (limit,))

    def cycle_times(self, kind: str, limit: int = 1000) -> List[float]:
        rows = self._query('SELECT seconds FROM cycle_times WHERE kind=? ORDER BY id DESC '
                           'LIMIT ?', (kind, limit))
        return [r['seconds'] for r in reversed(rows)]

    # ------------------------------------------------------------------ counters
    def save_counters(self, values: Dict[str, float]) -> None:
        with self.lock:
            self.conn.executemany('INSERT OR REPLACE INTO counters VALUES (?,?)',
                                  list(values.items()))
            self.conn.commit()

    def load_counters(self) -> Dict[str, float]:
        return {r['key']: r['value'] for r in self._query('SELECT * FROM counters')}

    # ------------------------------------------------------------------ users / audit
    def add_user(self, name: str, role: str, pin: str) -> None:
        if role not in ROLES:
            raise ValueError(f'role must be one of {ROLES}')
        if not (pin.isdigit() and 4 <= len(pin) <= 8):
            raise ValueError('PIN must be 4-8 digits')
        salt = secrets.token_hex(8)
        self._exec('INSERT OR REPLACE INTO users VALUES (?,?,?,?,?,1)',
                   (name, role, hash_pin(pin, salt), salt, utcnow()))

    def check_pin(self, pin: str) -> Optional[dict]:
        """Return the (highest-role) user whose PIN matches, else None."""
        best = None
        for u in self._query('SELECT * FROM users WHERE active=1'):
            if secrets.compare_digest(hash_pin(pin, u['salt']), u['pin_hash']):
                if best is None or ROLE_LEVEL[u['role']] > ROLE_LEVEL[best['role']]:
                    best = {'name': u['name'], 'role': u['role']}
        return best

    def list_users(self) -> List[dict]:
        return self._query('SELECT name, role, created, active FROM users ORDER BY name')

    def delete_user(self, name: str) -> None:
        self._exec('DELETE FROM users WHERE name=?', (name,))

    def audit(self, user: str, action: str, detail) -> None:
        if not isinstance(detail, str):
            detail = json.dumps(detail, sort_keys=True)
        self._exec('INSERT INTO audit (ts, user, action, detail) VALUES (?,?,?,?)',
                   (utcnow(), user or '', action, detail))

    def audit_trail(self, limit: int = 500) -> List[dict]:
        return self._query('SELECT * FROM audit ORDER BY id DESC LIMIT ?', (limit,))

    # ------------------------------------------------------------------ export
    def export_csv(self, table: str, path: str) -> int:
        if table not in ('jobs', 'production_log', 'alarm_history', 'audit', 'cycle_times',
                         'recipes'):
            raise ValueError(f'cannot export {table}')
        rows = self._query(f'SELECT * FROM {table} ORDER BY 1')  # noqa: S608 (whitelisted)
        with open(path, 'w', newline='') as fh:
            if rows:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        return len(rows)

    def close(self) -> None:
        with self.lock:
            self.conn.close()
