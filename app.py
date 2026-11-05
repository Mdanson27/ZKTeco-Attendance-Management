"""AutoMinds Africa — ZKTeco attendance proof of concept.
LOCAL SIMULATION ONLY. No physical scanner is connected.
Never expose this prototype directly to the public internet.
"""
from __future__ import annotations

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime
import csv
import io
import json
import sqlite3
import threading
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "attendance.sqlite3"
HOST = "127.0.0.1"
PORT = 8765
WRITE_LOCK = threading.Lock()

EMPLOYEES = [
    (101, "Sarah Nakato", "Kampala HQ", "08:00"),
    (102, "John Kato", "Kampala HQ", "08:00"),
    (103, "Peter Mugisha", "Mbarara", "08:00"),
    (104, "Grace Auma", "Gulu", "08:00"),
    (105, "David Ssemanda", "Entebbe", "08:00"),
    (106, "Esther Nansubuga", "Mbarara", "08:00"),
    (107, "Brian Okello", "Gulu", "08:00"),
    (108, "Mercy Namutebi", "Kampala HQ", "08:00"),
]
BRANCHES = ["Kampala HQ", "Mbarara", "Gulu", "Entebbe"]

def db_connect():
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection

def initialize():
    with db_connect() as db:
        db.execute("""CREATE TABLE IF NOT EXISTS employees (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL, branch TEXT NOT NULL,
            shift TEXT NOT NULL)""")
        db.execute("""CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL,
            branch TEXT NOT NULL, event_type TEXT NOT NULL,
            event_time TEXT NOT NULL, source TEXT NOT NULL)""")
        db.execute("CREATE INDEX IF NOT EXISTS ix_events_employee_time ON events(employee_id, event_time)")
        db.executemany("INSERT OR IGNORE INTO employees VALUES (?, ?, ?, ?)", EMPLOYEES)

def today_key():
    return datetime.now().astimezone().date().isoformat()

def get_state():
    today = today_key()
    with db_connect() as db:
        employees = [dict(r) for r in db.execute("SELECT * FROM employees ORDER BY name")]
        events = [dict(r) for r in db.execute(
            """SELECT events.*, employees.name FROM events
               JOIN employees ON employees.id = events.employee_id
               WHERE substr(events.event_time, 1, 10) = ?
               ORDER BY events.id DESC""", (today,))]
    current = {}
    for e in events:
        current.setdefault(e["employee_id"], e["event_type"])
    checked_in = sum(1 for action in current.values() if action == "IN")
    late = sum(1 for e in events
               if e["event_type"] == "IN" and e["event_time"][11:16] > "08:10")
    return {
        "demo": True, "hardware_connected": False, "date": today,
        "employees": employees, "branches": BRANCHES, "events": events,
        "metrics": {"total": len(employees), "present": checked_in,
                    "not_in": len(employees) - checked_in, "late": late}
    }

def simulate_scan(employee_id):
    with WRITE_LOCK:
        now = datetime.now().astimezone().isoformat(timespec="seconds")
        with db_connect() as db:
            employee = db.execute("SELECT * FROM employees WHERE id=?", (employee_id,)).fetchone()
            if employee is None:
                return None
            last = db.execute(
                """SELECT event_type FROM events WHERE employee_id=?
                   AND substr(event_time,1,10)=? ORDER BY id DESC LIMIT 1""",
                (employee_id, today_key())).fetchone()
            event_type = "OUT" if last and last["event_type"] == "IN" else "IN"
            db.execute("""INSERT INTO events
                (employee_id, branch, event_type, event_time, source)
                VALUES (?, ?, ?, ?, ?)""",
                (employee_id, employee["branch"], event_type, now, "SIMULATED"))
            return {"name": employee["name"], "event_type": event_type,
                    "event_time": now, "source": "SIMULATED"}

class Handler(BaseHTTPRequestHandler):
    def respond(self, status, content, content_type="application/json; charset=utf-8"):
        body = content.encode("utf-8") if isinstance(content, str) else content
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            return self.respond(200, (ROOT / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/assets/logo.jpeg":
            return self.respond(200, (ROOT / "autominds-logo.jpeg").read_bytes(), "image/jpeg")
        if path == "/api/health":
            return self.respond(200, json.dumps({"status": "ok", "mode": "simulation",
                                                 "hardware_connected": False}))
        if path == "/api/state":
            return self.respond(200, json.dumps(get_state()))
        if path == "/api/export":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["Employee", "Branch", "Event", "Local timestamp", "Source"])
            for event in get_state()["events"]:
                writer.writerow([event["name"], event["branch"], event["event_type"],
                                 event["event_time"], event["source"]])
            return self.respond(200, output.getvalue(), "text/csv; charset=utf-8")
        return self.respond(404, json.dumps({"error": "Not found"}))

    def do_POST(self):
        if urlparse(self.path).path != "/api/scan":
            return self.respond(404, json.dumps({"error": "Not found"}))
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 4096:
                raise ValueError("Invalid request size")
            obj = json.loads(self.rfile.read(size))
            employee_id = int(obj["employee_id"])
            result = simulate_scan(employee_id)
            if result is None:
                return self.respond(404, json.dumps({"error": "Employee not found"}))
            return self.respond(200, json.dumps(result))
        except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
            return self.respond(400, json.dumps({"error": str(exc)}))

    def log_message(self, fmt, *args):
        pass

if __name__ == "__main__":
    initialize()
    print(f"AutoMinds Africa Attendance Demo: http://{HOST}:{PORT}/", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
