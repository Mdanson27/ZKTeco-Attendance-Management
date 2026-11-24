import hashlib
import json
from datetime import timezone
from unittest.mock import patch
import pytest
from fastapi.testclient import TestClient
from .adms_protocol import parse_attlog, MAX_BODY
from .receiver import app

BODY = b"007\t2026-11-24 08:00:00\t0\t1\t0"
ORG = "11111111-1111-4111-8111-111111111111"
TOKEN = "synthetic-test-token-not-a-production-secret"

@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("ADMS_DEVICE_REGISTRY",json.dumps({"TEST01":{"organization_id":ORG,"token_sha256":hashlib.sha256(TOKEN.encode()).hexdigest()}}))
    return TestClient(app)

def test_timezone_and_replay():
    p = parse_attlog(BODY,"Africa/Kampala")[0]
    assert p.pin=="007"
    assert p.occurred_at.hour==5 and p.occurred_at.tzinfo==timezone.utc
    assert p.dedup_key==parse_attlog(BODY,"Africa/Kampala")[0].dedup_key

@pytest.mark.parametrize("body",[b"invalid",b"007\tinvalid",b"\t2026-11-24 08:00:00",b"007\t2026-11-24 08:00:00\tBAD",b"x"*(MAX_BODY+1)])
def test_bad_payload(body):
    with pytest.raises(ValueError):
        parse_attlog(body,"Africa/Kampala")

def test_unknown_device(client):
    assert client.get("/iclock/getrequest?SN=UNKNOWN").status_code==403

def test_missing_token(client):
    assert client.get("/iclock/getrequest?SN=TEST01").status_code==403

def test_unsupported_table(client):
    assert client.post("/iclock/cdata?SN=TEST01&table=USERINFO",headers={"X-Device-Token":TOKEN},content=BODY).status_code==400

def test_upload_dispatch(client):
    with patch("backend.receiver.transact",return_value="OK: 1") as store:
        r=client.post("/iclock/cdata?SN=TEST01&table=ATTLOG",headers={"X-Device-Token":TOKEN},content=BODY)
        assert r.status_code==200 and r.text=="OK: 1"
        store.assert_called_once_with("TEST01",ORG,"upload",BODY)

def test_oversize(client):
    assert client.post("/iclock/cdata?SN=TEST01&table=ATTLOG",headers={"X-Device-Token":TOKEN},content=b"x"*(MAX_BODY+1)).status_code==413
