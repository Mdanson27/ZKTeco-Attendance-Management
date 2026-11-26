"""Synthetic protocol exercise only. Never use real employee data here."""
import argparse
import os
import time
from datetime import datetime,timedelta
import httpx

def replay(base, serial, token, count=20419, batch=250):
    if not 1<=count<=100000 or not 1<=batch<=500:
        raise ValueError("Invalid replay bounds")
    if not base.startswith(("http://127.0.0.1:","https://")):
        raise ValueError("Use loopback or HTTPS")
    if not serial.startswith("TEST"):
        raise ValueError("Synthetic scanner serial required")
    with httpx.Client(base_url=base,headers={"X-Device-Token":token},timeout=15,follow_redirects=False) as client:
        for path,params in [("/iclock/cdata",{"SN":serial,"options":"all"}),("/iclock/getrequest",{"SN":serial})]:
            client.get(path,params=params).raise_for_status()
        for offset in range(0,count,batch):
            n=min(batch,count-offset)
            rows=[]
            for i in range(offset,offset+n):
                stamp=datetime(2025,1,1,8)+timedelta(minutes=i)
                rows.append(f"{i%56+1:03d}\t{stamp:%Y-%m-%d %H:%M:%S}\t0\t1\t0")
            body="\n".join(rows).encode()
            for attempt in range(5):
                try:
                    r=client.post("/iclock/cdata",params={"SN":serial,"table":"ATTLOG"},content=body)
                    if r.status_code==200 and r.text.strip()==f"OK: {n}":
                        break
                    if r.status_code not in (429,500,502,503,504):
                        raise RuntimeError("Unexpected acknowledgement")
                except httpx.TransportError:
                    pass
                if attempt==4:
                    raise RuntimeError("Replay stopped without acknowledgement")
                time.sleep(2**attempt)
            print(f"Acknowledged {offset+n}/{count} synthetic rows",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--base",default="http://127.0.0.1:8765")
    p.add_argument("--serial",required=True)
    p.add_argument("--count",type=int,default=20419)
    a=p.parse_args()
    replay(a.base,a.serial,os.environ["ADMS_TEST_TOKEN"],a.count)
