"""Device service for trusted backend callers; not a public HTTP API.
Caller must derive subject from a verified session, never from request JSON.
"""
from contextlib import contextmanager
from uuid import UUID
from zoneinfo import ZoneInfo
import os
import re
import psycopg
from psycopg.rows import dict_row

@contextmanager
def device_session(organization, subject, write=False):
    organization = str(UUID(str(organization)))
    if not subject:
        raise PermissionError("Authentication required")
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.organization_id', %s, true)", (organization,))
            cur.execute("""SELECT role, branch_id FROM attendance.memberships
                WHERE organization_id=%s AND identity_subject=%s AND active""",
                (organization, subject))
            member = cur.fetchone()
            if not member or (write and member["role"] not in ("owner","hr_admin")):
                raise PermissionError("Insufficient permissions")
            yield cur, organization, member

def list_devices(organization, subject):
    with device_session(organization, subject) as (cur, org, member):
        cur.execute("""SELECT d.id,d.serial_number,d.label,d.model,d.firmware,
            d.branch_id,b.name AS branch_name,d.enabled,d.test_only,d.last_seen_at,
            CASE WHEN NOT d.enabled THEN 'disabled'
                 WHEN d.last_seen_at IS NULL THEN 'never_connected'
                 WHEN d.last_seen_at >= now()-interval '120 seconds' THEN 'recently_seen'
                 ELSE 'stale' END AS connection_status
            FROM attendance.devices d JOIN attendance.branches b
            ON b.organization_id=d.organization_id AND b.id=d.branch_id
            WHERE d.organization_id=%s AND (%s::uuid IS NULL OR d.branch_id=%s::uuid)
            ORDER BY b.name,d.label,d.id""",(org,member["branch_id"],member["branch_id"]))
        return cur.fetchall()

def audit(cur, org, subject, action, device_id):
    cur.execute("""INSERT INTO attendance.audit_logs
        (organization_id,actor_subject,action,entity_type,entity_id)
        VALUES (%s,%s,%s,'device',%s)""",(org,subject,action,str(device_id)))

def register_device(organization, subject, branch_id, serial, label, model="ZKTeco F18", timezone="Africa/Kampala", test_only=False):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}",serial):
        raise ValueError("Invalid serial number")
    if not label.strip() or len(label)>120 or not model.strip() or len(model)>120:
        raise ValueError("Invalid device label or model")
    ZoneInfo(timezone)
    branch_id=str(UUID(str(branch_id)))
    with device_session(organization,subject,write=True) as (cur,org,member):
        if member["branch_id"] is not None and str(member["branch_id"])!=branch_id:
            raise PermissionError("Branch restricted")
        cur.execute("SELECT id FROM attendance.branches WHERE organization_id=%s AND id=%s AND active",(org,branch_id))
        if not cur.fetchone():
            raise ValueError("Unknown or inactive branch")
        cur.execute("""INSERT INTO attendance.devices
            (organization_id,branch_id,serial_number,label,model,timezone,test_only,enabled)
            VALUES (%s,%s,%s,%s,%s,%s,%s,false) RETURNING id,serial_number,enabled""",
            (org,branch_id,serial,label.strip(),model.strip(),timezone,test_only))
        device=cur.fetchone()
        audit(cur,org,subject,"device.register",device["id"])
        return device

def set_enabled(organization,subject,device_id,enabled):
    if type(enabled) is not bool:
        raise ValueError("Boolean required")
    with device_session(organization,subject,write=True) as (cur,org,member):
        cur.execute("""UPDATE attendance.devices SET enabled=%s
            WHERE organization_id=%s AND id=%s AND
            (%s::uuid IS NULL OR branch_id=%s::uuid)
            RETURNING id,enabled""",(enabled,org,str(UUID(str(device_id))),member["branch_id"],member["branch_id"]))
        device=cur.fetchone()
        if not device:
            raise LookupError("Device not found")
        audit(cur,org,subject,"device.enable" if enabled else "device.disable",device["id"])
        return device

def connection_history(organization,subject,device_id,limit=100):
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("Limit must be 1–500")
    with device_session(organization,subject) as (cur,org,member):
        cur.execute("""SELECT l.id,l.occurred_at,l.event_type
            FROM attendance.device_connection_logs l JOIN attendance.devices d
            ON d.organization_id=l.organization_id AND d.id=l.device_id
            WHERE l.organization_id=%s AND d.id=%s AND
            (%s::uuid IS NULL OR d.branch_id=%s::uuid)
            ORDER BY l.occurred_at DESC,l.id DESC LIMIT %s""",
            (org,str(UUID(str(device_id))),member["branch_id"],member["branch_id"],limit))
        return cur.fetchall()
