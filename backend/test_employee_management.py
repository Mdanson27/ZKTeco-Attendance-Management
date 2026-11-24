import pytest
from .employee_management import clean, scope, uid, bulk_register, list_employees

@pytest.mark.parametrize("value",["", "   ", "a\nb", None, 123, "x"*121])
def test_invalid_text(value):
    with pytest.raises(ValueError):
        clean(value)

def test_preserve_leading_zero():
    assert clean("007",64)=="007"

def test_branch_scope():
    scope({"branch_id":None},"other")
    scope({"branch_id":"a"},"a")
    with pytest.raises(PermissionError):
        scope({"branch_id":"a"},"b")

@pytest.mark.parametrize("rows",[[],[{}]*501,None])
def test_batch_bounds(rows):
    with pytest.raises(ValueError):
        bulk_register("org","subject",rows)

def test_pagination_bounds():
    with pytest.raises(ValueError):
        list_employees("org","subject",limit=501)

def test_invalid_uuid():
    with pytest.raises(ValueError):
        uid("not-a-uuid")
