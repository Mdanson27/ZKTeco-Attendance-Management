"""Dashboard API: verify Neon session server-side, then enforce membership on every query."""
import os
import csv
import io
from datetime import datetime, timedelta, timezone
from uuid import UUID
import httpx
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from fastapi.responses import StreamingResponse
from .device_management import device_session, list_devices
from .employee_management import list_employees

router=APIRouter(prefix="/api/workspace")

async def subject(authorization: str=Header(default="")):
    if not authorization.startswith("Bearer ") or len(authorization)>8192:
        raise HTTPException(401,"Sign in required")
    url=os.environ.get("NEON_AUTH_URL")
    if not url:
        raise HTTPException(503,"Authentication not configured")
    try:
        async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client:
            response=await client.get(url.rstrip("/")+"/get-session",headers={"Authorization":authorization})
        if response.status_code!=200:
            raise HTTPException(401,"Invalid session")
        data=response.json()
        user=data.get("user") or {}
        session=data.get("session") or {}
        if not user.get("id") or str(session.get("userId"))!=str(user["id"]) or user.get("emailVerified") is not True:
            raise HTTPException(401,"Verified session required")
        expires=datetime.fromisoformat(session["expiresAt"].replace("Z","+00:00"))
        if expires<=datetime.now(timezone.utc):
            raise HTTPException(401,"Session expired")
        return str(user["id"])
    except (httpx.HTTPError,ValueError,KeyError,TypeError,AttributeError):
        raise HTTPException(503,"Authentication unavailable")

def safe_call(fn,*args):
    try:
        return fn(*args)
    except PermissionError:
        raise HTTPException(403,"Workspace access denied")
    except psycopg.Error:
        raise HTTPException(503,"Database unavailable")

def attendance_rows(org,actor,start,end,limit,offset=0):
    if start.tzinfo is None or end.tzinfo is None or end<=start or end-start>timedelta(days=31):
        raise HTTPException(400,"Use an explicit timezone and a range up to 31 days")
    with device_session(org,actor) as (cur,org,m):
        cur.execute("""SELECT r.id,r.occurred_at,r.device_pin,b.name AS branch,
          d.label AS device,e.employee_number,e.full_name,
          coalesce(p.interpretation,'unresolved') AS interpretation,
          coalesce(p.processing_status,'pending') AS processing_status
          FROM attendance.raw_events r
          JOIN attendance.branches b ON (b.organization_id,b.id)=(r.organization_id,r.branch_id)
          JOIN attendance.devices d ON (d.organization_id,d.id)=(r.organization_id,r.device_id)
          LEFT JOIN attendance.processed_events p ON (p.organization_id,p.raw_event_id)=(r.organization_id,r.id)
          LEFT JOIN attendance.employees e ON (e.organization_id,e.id)=(p.organization_id,p.employee_id)
            AND (%s::uuid IS NULL OR e.branch_id=%s::uuid)
          WHERE r.organization_id=%s AND r.source='device'
            AND r.occurred_at >= %s AND r.occurred_at < %s
            AND (%s::uuid IS NULL OR r.branch_id=%s::uuid)
          ORDER BY r.occurred_at DESC,r.id DESC LIMIT %s OFFSET %s""",
          (m["branch_id"],m["branch_id"],org,start,end,m["branch_id"],m["branch_id"],limit,offset))
        return cur.fetchall()

@router.get("/{org}/attendance")
def attendance(org: UUID,start: datetime,end: datetime,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor=Depends(subject)):
    return safe_call(attendance_rows,org,actor,start,end,limit,offset)

@router.get("/{org}/employees")
def employees(org:UUID,limit:int=Query(100,ge=1,le=500),offset:int=Query(0,ge=0),actor=Depends(subject)):
    return safe_call(list_employees,org,actor,limit,offset)

@router.get("/{org}/devices")
def devices(org:UUID,actor=Depends(subject)):
    return [r for r in safe_call(list_devices,org,actor) if not r["test_only"]]

def overview_data(org,actor):
    with device_session(org,actor) as (cur,org,m):
        branch=m["branch_id"]
        cur.execute("""SELECT
          (SELECT count(*) FROM attendance.employees WHERE organization_id=%s AND active AND (%s::uuid IS NULL OR branch_id=%s::uuid)) AS active_employees,
          (SELECT count(*) FROM attendance.devices WHERE organization_id=%s AND NOT test_only AND (%s::uuid IS NULL OR branch_id=%s::uuid)) AS devices,
          (SELECT count(*) FROM attendance.devices WHERE organization_id=%s AND NOT test_only AND enabled AND last_seen_at>=now()-interval '120 seconds' AND (%s::uuid IS NULL OR branch_id=%s::uuid)) AS recently_seen,
          (SELECT count(*) FROM attendance.raw_events WHERE organization_id=%s AND source='device' AND received_at>=now()-interval '24 hours' AND (%s::uuid IS NULL OR branch_id=%s::uuid)) AS received_24h""",
          (org,branch,branch)*4)
        return cur.fetchone()

@router.get("/{org}/overview")
def overview(org:UUID,actor=Depends(subject)):
    return safe_call(overview_data,org,actor)

def csv_cell(value):
    s="" if value is None else str(value)
    return "'"+s if s.lstrip().startswith(("=","+","-","@")) or s.startswith(("\t","\r","\n")) else s

@router.get("/{org}/report.csv")
def report(org:UUID,start:datetime,end:datetime,actor=Depends(subject)):
    rows=safe_call(attendance_rows,org,actor,start,end,10001)
    if len(rows)>10000:
        raise HTTPException(413,"Select a shorter date range")
    cols=["occurred_at","employee_number","full_name","device_pin","branch","device","interpretation","processing_status"]
    output=io.StringIO()
    writer=csv.writer(output)
    writer.writerow(cols)
    writer.writerows([[csv_cell(row[c]) for c in cols] for row in rows])
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=attendance.csv","Cache-Control":"no-store"})
