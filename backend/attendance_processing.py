"""Pure attendance calculation engine. No guessed punch directions or payroll approval."""
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

@dataclass(frozen=True)
class Event:
    at: datetime
    kind: str

def shift_window(day: date, start: time, end: time, zone: str):
    tz = ZoneInfo(zone)
    if start == end or start.tzinfo or end.tzinfo:
        raise ValueError("Shift must have distinct local times")
    def convert(d,t):
        local = datetime.combine(d,t)
        a = local.replace(tzinfo=tz)
        if a.utcoffset()!=local.replace(tzinfo=tz,fold=1).utcoffset() or a.astimezone(timezone.utc).astimezone(tz).replace(tzinfo=None)!=local:
            raise ValueError("Ambiguous shift boundary")
        return a.astimezone(timezone.utc)
    return convert(day,start),convert(day+timedelta(days=int(end<start)),end)

def summarize(events, start, end, as_of, grace_minutes=10, coverage_verified=False, excused=False):
    """Events must be assigned to this shift by an authorized upstream process.
    Durations are integer seconds. Overtime is a candidate, not payroll entitlement.
    """
    def utc(t):
        if t.tzinfo is None or t.utcoffset() is None:
            raise ValueError("Timezone-aware timestamp required")
        return t.astimezone(timezone.utc)
    start,end,as_of=map(utc,(start,end,as_of))
    if end<=start or type(grace_minutes) is not int or not 0<=grace_minutes<=180:
        raise ValueError("Invalid shift")
    rows=sorted((Event(utc(e.at),e.kind) for e in events),key=lambda e:e.at)
    issues=[]
    state="outside"
    opened=None
    first_in=None
    last_out=None
    intervals=[]
    for e in rows:
        if e.at>as_of:
            issues.append("future_punch")
            continue
        if e.kind=="check_in" and state=="outside":
            opened=e.at
            first_in=first_in or e.at
            state="working"
        elif e.kind=="break_start" and state=="working":
            intervals.append((opened,e.at))
            opened=None
            state="break"
        elif e.kind=="break_end" and state=="break":
            opened=e.at
            state="working"
        elif e.kind=="check_out" and state=="working":
            intervals.append((opened,e.at))
            opened=None
            last_out=e.at
            state="outside"
        else:
            issues.append("unexpected_"+e.kind)
    if state!="outside" and as_of>=end:
        issues.append("missing_checkout" if state=="working" else "unfinished_break")
    worked=sum(int((b-a).total_seconds()) for a,b in intervals)
    scheduled_overlap=sum(max(0,int((min(b,end)-max(a,start)).total_seconds())) for a,b in intervals)
    if issues or (excused and rows):
        status="review"
    elif not rows:
        status="excused" if excused else "scheduled" if as_of<start else "awaiting_punch" if as_of<end else "absent" if coverage_verified else "coverage_unverified"
    elif state!="outside" or as_of<end:
        status="in_progress"
    else:
        status="complete"
    late=max(0,int((first_in-start).total_seconds())) if first_in and first_in>start+timedelta(minutes=grace_minutes) else 0
    early=max(0,int((end-last_out).total_seconds())) if status=="complete" and last_out else None
    return {"status":status,"worked_seconds":worked,"late_seconds":late if first_in else None,
            "early_departure_seconds":early,"outside_shift_seconds":worked-scheduled_overlap,
            "first_in":first_in,"last_out":last_out,"issues":sorted(set(issues)),
            "provisional":status!="complete" or not coverage_verified}
