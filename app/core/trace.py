import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


def generate_trace_id() -> str:
    tid = uuid.uuid4().hex
    trace_id_var.set(tid)
    return tid


def get_trace_id() -> str:
    return trace_id_var.get()
