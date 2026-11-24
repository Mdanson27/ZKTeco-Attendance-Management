"""Experimental receiver. Run behind private VPN or authenticated TLS proxy.
No live hardware enabled unless explicitly configured. Never trust forwarded headers.
"""
import os
import re
import json
import hmac
from hashlib import sha256
from uuid import UUID
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse
import psycopg
from psycopg.rows import dict_row
from starlette.concurrency import run_in_threadpool
from .adms_protocol import parse_attlog, initialization, MAX_BODY

app = FastAPI(title="AutoMinds ADMS", docs_url=None, redoc_url=None, openapi_url=None)

def admission(request):
    serial = request.query_params.get("SN", "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", serial):
        raise HTTPException(400, "Invalid serial")
    # Private server-side registry binds serial to tenant and high-entropy token.
    # A future VPN adapter must authenticate peer identity before injecting token.
    registry = json.loads(os.getenv("ADMS_DEVICE_REGISTRY", "{}"))
    item = registry.get(serial)
    supplied = request.headers.get("X-Device-Token", "")
    if not item or len(supplied) > 512 or not hmac.compare_digest(
        sha256(supplied.encode()).hexdigest(), item["token_sha256"]
    ):
        raise HTTPException(403, "Device not authorized")
    return serial, str(UUID(item["organization_id"]))

def transact(serial, organization, action, body=b""):
    with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.organization_id', %s, true)", (organization,))
            cur.execute("""SELECT id, organization_id, branch_id, timezone, test_only
                FROM attendance.devices WHERE serial_number=%s AND enabled FOR UPDATE""", (serial,))
            device = cur.fetchone()
            if not device:
                raise HTTPException(403, "Device not authorized")
            if not device["test_only"] and os.getenv("ADMS_ENABLE_LIVE") != "true":
                raise HTTPException(403, "Live hardware disabled")
            if action == "upload":
                try:
                    punches = parse_attlog(body, device["timezone"])
                except (ValueError, KeyError):
                    raise HTTPException(400, "Invalid attendance payload")
                source = "protocol_test" if device["test_only"] else "device"
                for p in punches:
                    cur.execute("""INSERT INTO attendance.raw_events
                      (organization_id,device_id,branch_id,device_pin,device_local_time,
                       occurred_at,punch_code,verify_code,work_code,source,dedup_key)
                      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                      ON CONFLICT (device_id,source,dedup_key) DO NOTHING""",
                      (organization,device["id"],device["branch_id"],p.pin,p.local_time,
                       p.occurred_at,p.status,p.verify,p.work,source,p.dedup_key))
                reply = f"OK: {len(punches)}"
            elif action == "initialize":
                reply = initialization(serial)
            else:
                reply = "OK"
            cur.execute("UPDATE attendance.devices SET last_seen_at=now() WHERE id=%s",(device["id"],))
            cur.execute("""INSERT INTO attendance.device_connection_logs
                (organization_id,device_id,event_type) VALUES (%s,%s,%s)""",
                (organization,device["id"],action))
        # Connection context commits before returning acknowledgement.
    return reply

async def bounded_body(request):
    body = bytearray()
    async for chunk in request.stream():
        if len(body)+len(chunk)>MAX_BODY:
            raise HTTPException(413, "Payload too large")
        body.extend(chunk)
    return bytes(body)

async def handle(request, action, body=b""):
    serial, org = admission(request)
    try:
        result = await run_in_threadpool(transact, serial, org, action, body)
    except psycopg.Error:
        raise HTTPException(503, "Storage unavailable; retry")
    return PlainTextResponse(result)

@app.get("/api/health")
def health():
    return {"status":"running","mode":"experimental","live_enabled":os.getenv("ADMS_ENABLE_LIVE")=="true"}

@app.get("/iclock/cdata")
async def initialize(request: Request):
    if request.query_params.get("options") != "all":
        raise HTTPException(400, "Unsupported initialization")
    return await handle(request,"initialize")

@app.post("/iclock/cdata")
async def upload(request: Request):
    admission(request)
    if request.query_params.get("table") != "ATTLOG":
        raise HTTPException(400, "Unsupported table")
    return await handle(request,"upload",await bounded_body(request))

@app.get("/iclock/getrequest")
async def poll(request: Request):
    return await handle(request,"heartbeat")

@app.post("/iclock/devicecmd")
async def acknowledge(request: Request):
    admission(request)
    await bounded_body(request)
    # No commands are issued or acted upon in this experimental receiver.
    return await handle(request,"command_ack")

from .dashboard import router as dashboard_router
app.include_router(dashboard_router)
