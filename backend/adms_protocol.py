"""Experimental TA PUSH parser; validate against actual F18 firmware before deployment."""
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
import json

MAX_BODY = 262144
MAX_ROWS = 2000

@dataclass(frozen=True)
class Punch:
    pin: str
    local_time: datetime
    occurred_at: datetime
    status: str
    verify: str
    work: str
    dedup_key: str

def parse_attlog(body: bytes, zone: str) -> list[Punch]:
    if len(body) > MAX_BODY:
        raise ValueError("payload too large")
    tz = ZoneInfo(zone)
    rows = body.decode("utf-8", errors="strict").splitlines()
    if len(rows) > MAX_ROWS:
        raise ValueError("too many records")
    result = []
    for row in rows:
        if not row.strip():
            continue
        fields = row.split("\t")
        if not 2 <= len(fields) <= 8:
            raise ValueError("unsupported attendance row")
        pin, stamp = fields[:2]
        if not pin or len(pin)>64 or any(ord(c)<32 for c in pin):
            raise ValueError("invalid employee PIN")
        local = datetime.strptime(stamp, "%Y-%m-%d %H:%M:%S")
        aware = local.replace(tzinfo=tz)
        if aware.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=local or local.replace(tzinfo=tz,fold=0).utcoffset()!=local.replace(tzinfo=tz,fold=1).utcoffset():
            raise ValueError("ambiguous or invalid local time")
        codes = (fields[2:5]+["","",""])[:3]
        if any(len(c)>32 or (c and not c.isascii()) or (c and not c.isdigit()) for c in codes):
            raise ValueError("invalid attendance code")
        key = sha256(json.dumps([pin,stamp,*codes],separators=(",",":")).encode()).hexdigest()
        result.append(Punch(pin,local,aware.astimezone(timezone.utc),*codes,key))
    return result

def initialization(serial: str) -> str:
    # Provisional TA PUSH response; do not reset device cursors or command deletion.
    return f"GET OPTION FROM: {serial}\nErrorDelay=60\nDelay=30\nRealtime=1\n"
