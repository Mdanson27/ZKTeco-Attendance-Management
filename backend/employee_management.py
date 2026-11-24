"""Employee operations for trusted callers with verified session subjects."""
from uuid import UUID
from .device_management import device_session

def uid(value):
    return str(UUID(str(value)))

def clean(value, limit=120):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 for c in value):
        raise ValueError("Invalid text field")
    return value.strip()

def scope(member, branch):
    if member["branch_id"] is not None and str(member["branch_id"])!=str(branch):
        raise PermissionError("Branch restricted")

def audit(cur,org,subject,action,entity,id):
    cur.execute("""INSERT INTO attendance.audit_logs
      (organization_id,actor_subject,action,entity_type,entity_id)
      VALUES (%s,%s,%s,%s,%s)""",(org,subject,action,entity,str(id)))

def list_employees(organization,subject,limit=100,offset=0):
    if type(limit) is not int or not 1<=limit<=500 or type(offset) is not int or offset<0:
        raise ValueError("Invalid pagination")
    with device_session(organization,subject) as (cur,org,m):
        cur.execute("""SELECT e.id,e.employee_number,e.full_name,e.active,e.branch_id,
          b.name AS branch_name,e.department_id,d.name AS department_name
          FROM attendance.employees e JOIN attendance.branches b
          ON (b.organization_id,b.id)=(e.organization_id,e.branch_id)
          LEFT JOIN attendance.departments d ON (d.organization_id,d.id)=(e.organization_id,e.department_id)
          WHERE e.organization_id=%s AND (%s::uuid IS NULL OR e.branch_id=%s::uuid)
          ORDER BY e.employee_number,e.id LIMIT %s OFFSET %s""",
          (org,m["branch_id"],m["branch_id"],limit,offset))
        return cur.fetchall()

def create_department(organization,subject,name):
    with device_session(organization,subject,write=True) as (cur,org,m):
        if m["branch_id"] is not None:
            raise PermissionError("Organization-wide permission required")
        cur.execute("INSERT INTO attendance.departments (organization_id,name) VALUES (%s,%s) RETURNING id,name",(org,clean(name)))
        row=cur.fetchone()
        audit(cur,org,subject,"department.create","department",row["id"])
        return row

def _insert(cur,org,m,subject,employee_number,full_name,branch_id,department_id=None):
    branch=uid(branch_id)
    scope(m,branch)
    cur.execute("SELECT id FROM attendance.branches WHERE organization_id=%s AND id=%s AND active",(org,branch))
    if not cur.fetchone():
        raise ValueError("Unknown or inactive branch")
    cur.execute("""INSERT INTO attendance.employees
      (organization_id,employee_number,full_name,branch_id,department_id)
      VALUES (%s,%s,%s,%s,%s) RETURNING id,employee_number,full_name,active""",
      (org,clean(employee_number,64),clean(full_name,200),branch,uid(department_id) if department_id else None))
    row=cur.fetchone()
    audit(cur,org,subject,"employee.create","employee",row["id"])
    return row

def register_employee(organization,subject,employee_number,full_name,branch_id,department_id=None):
    with device_session(organization,subject,write=True) as (cur,org,m):
        return _insert(cur,org,m,subject,employee_number,full_name,branch_id,department_id)

def bulk_register(organization,subject,rows):
    """Atomic batch; spreadsheet parsing is a separate adapter."""
    if not isinstance(rows,list) or not 1<=len(rows)<=500:
        raise ValueError("Batch must contain 1–500 rows")
    with device_session(organization,subject,write=True) as (cur,org,m):
        return [_insert(cur,org,m,subject,**row) for row in rows]

def set_employee_active(organization,subject,employee_id,active):
    if type(active) is not bool:
        raise ValueError("Boolean required")
    with device_session(organization,subject,write=True) as (cur,org,m):
        cur.execute("""UPDATE attendance.employees SET active=%s WHERE organization_id=%s AND id=%s
          AND (%s::uuid IS NULL OR branch_id=%s::uuid) RETURNING id,active""",
          (active,org,uid(employee_id),m["branch_id"],m["branch_id"]))
        row=cur.fetchone()
        if not row:
            raise LookupError("Employee not found")
        audit(cur,org,subject,"employee.activate" if active else "employee.deactivate","employee",row["id"])
        return row

def map_pin(organization,subject,employee_id,device_id,pin):
    """No silent reassignment: a conflicting device PIN raises a unique violation."""
    pin=clean(pin,64)
    with device_session(organization,subject,write=True) as (cur,org,m):
        cur.execute("SELECT branch_id,active FROM attendance.employees WHERE organization_id=%s AND id=%s",(org,uid(employee_id)))
        employee=cur.fetchone()
        cur.execute("SELECT branch_id FROM attendance.devices WHERE organization_id=%s AND id=%s",(org,uid(device_id)))
        device=cur.fetchone()
        if not employee or not employee["active"] or not device:
            raise ValueError("Unknown device or inactive employee")
        scope(m,employee["branch_id"])
        scope(m,device["branch_id"])
        cur.execute("""INSERT INTO attendance.device_employee_mappings
          (organization_id,device_id,employee_id,device_pin) VALUES (%s,%s,%s,%s)
          RETURNING device_id,employee_id,device_pin""",(org,uid(device_id),uid(employee_id),pin))
        row=cur.fetchone()
        audit(cur,org,subject,"employee.map_pin","employee",employee_id)
        return row

def unresolved_pins(organization,subject,limit=100):
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("Invalid limit")
    with device_session(organization,subject) as (cur,org,m):
        cur.execute("""SELECT r.device_id,r.device_pin,count(*) AS punches,max(r.occurred_at) AS last_seen
          FROM attendance.raw_events r LEFT JOIN attendance.device_employee_mappings p
          ON (p.organization_id,p.device_id,p.device_pin)=(r.organization_id,r.device_id,r.device_pin)
          WHERE r.organization_id=%s AND r.source='device' AND p.employee_id IS NULL
          AND (%s::uuid IS NULL OR r.branch_id=%s::uuid)
          GROUP BY r.device_id,r.device_pin ORDER BY last_seen DESC LIMIT %s""",
          (org,m["branch_id"],m["branch_id"],limit))
        return cur.fetchall()

def attendance_history(organization,subject,employee_id,limit=100):
    """Only finalized identity associations; never retroactively join current PIN mappings."""
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("Invalid limit")
    with device_session(organization,subject) as (cur,org,m):
        cur.execute("""SELECT branch_id FROM attendance.employees WHERE organization_id=%s AND id=%s""",(org,uid(employee_id)))
        employee=cur.fetchone()
        if not employee:
            raise LookupError("Employee not found")
        scope(m,employee["branch_id"])
        cur.execute("""SELECT r.id,r.occurred_at,r.branch_id,r.device_id,p.interpretation,p.processing_status
          FROM attendance.processed_events p JOIN attendance.raw_events r
          ON (r.organization_id,r.id)=(p.organization_id,p.raw_event_id)
          WHERE p.organization_id=%s AND p.employee_id=%s AND r.source='device'
          AND (%s::uuid IS NULL OR r.branch_id=%s::uuid)
          ORDER BY r.occurred_at DESC,r.id DESC LIMIT %s""",
          (org,uid(employee_id),m["branch_id"],m["branch_id"],limit))
        return cur.fetchall()
