"""Elevated broker client — Full-Trust admin without elevating the MCP.

The desktop process stays at medium integrity so UIA/clicks still work
(UIPI). Privileged OS work (HKLM, Program Files, services, …) is sent to a
loopback helper that runs as admin.

The helper is installed once as a Highest-Available logon task
(``ExoControl\\ElevatedBroker``). First use may show one UAC prompt. After
that, ``schtasks /Run`` starts it without another prompt.

Never run the MCP itself as admin.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
import xml.sax.saxutils
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

TASK_NAME = r"ExoControl\ElevatedBroker"
ENDPOINT_NAME = "elevate.json"
DEFAULT_TIMEOUT = 60.0
UAC_WAIT_SEC = 90.0
PING_WAIT_SEC = 8.0


def _truthy(value: Any) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_admin() -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def in_broker() -> bool:
    return _truthy(os.environ.get("EXO_ELEVATED_BROKER"))


def elevate_disabled() -> bool:
    return _truthy(os.environ.get("EXO_DISABLE_ELEVATE"))


def unrestricted() -> bool:
    """Owner mode: Full-Trust *or* this process *is* the elevated broker."""
    if in_broker():
        return True
    from exo_control.trust import full_trust_active

    return full_trust_active()


def should_escalate() -> bool:
    from exo_control.trust import human_kill_armed

    if elevate_disabled() or in_broker() or is_admin():
        return False
    if human_kill_armed():
        return False
    from exo_control.trust import full_trust_active

    return full_trust_active()


def looks_access_denied(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    blob = " ".join(
        str(result.get(k) or "")
        for k in ("error", "stderr", "stdout", "reason")
    ).lower()
    needles = (
        "access is denied",
        "access denied",
        "permissionerror",
        "permission denied",
        "winerror 5",
        "error 5",
        "error: 5",
        "requireshigher",
        "requested operation requires elevation",
        "privilege",
        "not privileged",
    )
    return any(n in blob for n in needles)


def endpoint_path() -> Path:
    from exo_control.paths import state_dir

    return state_dir() / ENDPOINT_NAME


def _restrict_user_only(path: Path) -> None:
    if os.name != "nt":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return
    user = os.environ.get("USERNAME") or ""
    if not user:
        return
    try:
        subprocess.run(
            ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(R,W)"],
            capture_output=True,
            text=True,
            timeout=8,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            check=False,
        )
    except Exception:
        pass


def write_endpoint(*, port: int, token: str, pid: int) -> Path:
    path = endpoint_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "port": int(port),
        "token": str(token),
        "pid": int(pid),
        "elevated": True,
        "ts": time.time(),
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)
    _restrict_user_only(path)
    return path


def read_endpoint() -> Optional[Dict[str, Any]]:
    path = endpoint_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not data.get("port") or not data.get("token"):
        return None
    return data


def _rpc(payload: Dict[str, Any], *, timeout: float = 15.0) -> Dict[str, Any]:
    ep = read_endpoint()
    if not ep:
        return {"ok": False, "error": "elevate_broker_offline", "hint": "no endpoint file"}
    raw = json.dumps(payload, ensure_ascii=False, default=str) + "\n"
    try:
        with socket.create_connection(("127.0.0.1", int(ep["port"])), timeout=timeout) as sock:
            sock.sendall(raw.encode("utf-8"))
            sock.shutdown(socket.SHUT_WR)
            chunks: List[bytes] = []
            sock.settimeout(timeout)
            while True:
                buf = sock.recv(65536)
                if not buf:
                    break
                chunks.append(buf)
        text = b"".join(chunks).decode("utf-8", errors="replace").strip()
        if not text:
            return {"ok": False, "error": "elevate_empty_response"}
        out = json.loads(text.splitlines()[-1])
        if isinstance(out, dict):
            return out
        return {"ok": False, "error": "elevate_bad_response", "raw": text[:300]}
    except Exception as exc:
        return {"ok": False, "error": f"elevate_rpc: {type(exc).__name__}: {exc}"}


def ping(timeout: float = 1.5) -> Dict[str, Any]:
    ep = read_endpoint()
    if not ep:
        return {"ok": False, "error": "offline"}
    out = _rpc({"token": ep["token"], "op": "ping"}, timeout=timeout)
    if out.get("ok"):
        out["port"] = ep.get("port")
        out["pid"] = ep.get("pid")
    return out


def python_exe() -> str:
    return os.path.abspath(sys.executable)


def broker_python_exe() -> str:
    """pythonw on Windows so the logon task does not open a console/WT tab."""
    exe = python_exe()
    if os.name == "nt":
        directory, name = os.path.split(exe)
        if name.lower() == "python.exe":
            pythonw = os.path.join(directory, "pythonw.exe")
            if os.path.isfile(pythonw):
                return os.path.abspath(pythonw)
    return exe


def task_exists() -> bool:
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["schtasks", "/Query", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            check=False,
        )
        return completed.returncode == 0
    except Exception:
        return False


def _task_xml(python: str) -> str:
    cmd = xml.sax.saxutils.escape(python)
    args = xml.sax.saxutils.escape("-m exo_control.elevated_broker --serve")
    return (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo>\n"
        "    <Description>Exo Control elevated broker. MCP stays medium IL.</Description>\n"
        "  </RegistrationInfo>\n"
        "  <Triggers>\n"
        "    <LogonTrigger>\n"
        "      <Enabled>true</Enabled>\n"
        "    </LogonTrigger>\n"
        "  </Triggers>\n"
        "  <Principals>\n"
        '    <Principal id="Author">\n'
        "      <LogonType>InteractiveToken</LogonType>\n"
        "      <RunLevel>HighestAvailable</RunLevel>\n"
        "    </Principal>\n"
        "  </Principals>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <AllowHardTerminate>false</AllowHardTerminate>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <AllowStartOnDemand>true</AllowStartOnDemand>\n"
        "    <Enabled>true</Enabled>\n"
        "    <Hidden>true</Hidden>\n"
        "    <ExecutionTimeLimit>PT0S</ExecutionTimeLimit>\n"
        "    <Priority>4</Priority>\n"
        "  </Settings>\n"
        '  <Actions Context="Author">\n'
        "    <Exec>\n"
        f"      <Command>{cmd}</Command>\n"
        f"      <Arguments>{args}</Arguments>\n"
        "    </Exec>\n"
        "  </Actions>\n"
        "</Task>\n"
    )


def install_task() -> Dict[str, Any]:
    """Create the Highest-Available logon task. Must already be admin."""
    if os.name != "nt":
        return {"ok": False, "error": "elevate install requires Windows"}
    if not is_admin():
        return {
            "ok": False,
            "error": "install_requires_admin",
            "hint": "run via UAC (ensure_broker) or an elevated shell",
        }
    from exo_control.paths import state_dir

    xml_path = state_dir() / "elevate-task.xml"
    xml_path.parent.mkdir(parents=True, exist_ok=True)
    broker_py = broker_python_exe()
    xml_path.write_bytes(_task_xml(broker_py).encode("utf-16"))
    try:
        completed = subprocess.run(
            ["schtasks", "/Create", "/TN", TASK_NAME, "/XML", str(xml_path), "/F"],
            capture_output=True,
            text=True,
            timeout=20,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ok = completed.returncode == 0
    return {
        "ok": ok,
        "task": TASK_NAME,
        "python": broker_py,
        "stdout": (completed.stdout or "").strip()[:400],
        "stderr": (completed.stderr or "").strip()[:400],
        "error": None if ok else ((completed.stderr or completed.stdout or "schtasks failed").strip()[:400]),
    }


def start_task() -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "Windows only"}
    if not task_exists():
        return {"ok": False, "error": "task_missing", "task": TASK_NAME}
    try:
        completed = subprocess.run(
            ["schtasks", "/Run", "/TN", TASK_NAME],
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
            check=False,
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    ok = completed.returncode == 0
    return {
        "ok": ok,
        "task": TASK_NAME,
        "stdout": (completed.stdout or "").strip()[:300],
        "error": None if ok else ((completed.stderr or completed.stdout or "run failed").strip()[:300]),
    }


def _shell_runas(args: str) -> Dict[str, Any]:
    """One UAC prompt. Starts an elevated broker; does not elevate this process."""
    if os.name != "nt":
        return {"ok": False, "error": "Windows only"}
    try:
        import ctypes

        rc = int(
            ctypes.windll.shell32.ShellExecuteW(
                None,
                "runas",
                python_exe(),
                args,
                None,
                0,
            )
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    if rc <= 32:
        return {
            "ok": False,
            "error": "uac_declined_or_failed",
            "shell_execute": rc,
            "hint": "Windows refused elevation (UAC no / cancelled)",
        }
    return {"ok": True, "shell_execute": rc, "spawned": True}


def _wait_ping(seconds: float) -> bool:
    deadline = time.time() + max(0.2, seconds)
    while time.time() < deadline:
        if ping(timeout=0.6).get("ok"):
            return True
        time.sleep(0.25)
    return False


def ensure_broker(*, uac: bool = True, timeout: float = UAC_WAIT_SEC) -> Dict[str, Any]:
    """Make sure the elevated helper is listening. May show one UAC prompt."""
    if in_broker():
        return {"ok": True, "mode": "local_admin", "admin": is_admin(), "broker": True}
    if is_admin():
        installed = None
        if not task_exists():
            installed = install_task()
        started = start_task() if task_exists() else {"ok": False, "error": "task_missing"}
        _wait_ping(PING_WAIT_SEC)
        return {
            "ok": True,
            "mode": "local_admin",
            "admin": True,
            "broker": False,
            "install_task": installed,
            "start": started,
            "broker_up": bool(ping(timeout=0.6).get("ok")),
        }
    if ping(timeout=0.8).get("ok"):
        return {"ok": True, "mode": "already_up", **(read_endpoint() or {})}
    started = start_task() if task_exists() else {"ok": False, "error": "task_missing"}
    if _wait_ping(PING_WAIT_SEC):
        return {"ok": True, "mode": "task", "start": started, **(read_endpoint() or {})}
    if not uac:
        return {
            "ok": False,
            "error": "elevate_broker_offline",
            "start": started,
            "hint": "pass uac=true or run: exo-control elevate install",
        }
    spawned = _shell_runas("-m exo_control.elevated_broker --serve --install")
    if not spawned.get("ok"):
        return spawned
    if _wait_ping(timeout):
        return {"ok": True, "mode": "uac", "spawned": True, **(read_endpoint() or {})}
    return {
        "ok": False,
        "error": "elevate_broker_timeout",
        "spawned": spawned,
        "hint": "UAC may have been dismissed; retry and accept the prompt",
    }


def status() -> Dict[str, Any]:
    ep = read_endpoint()
    live = ping(timeout=0.6)
    return {
        "ok": True,
        "admin": is_admin(),
        "in_broker": in_broker(),
        "unrestricted": unrestricted(),
        "should_escalate": should_escalate(),
        "disabled": elevate_disabled(),
        "task": TASK_NAME,
        "task_installed": task_exists(),
        "broker_up": bool(live.get("ok")),
        "endpoint": ({"port": ep.get("port"), "pid": ep.get("pid")} if ep else None),
        "hint": (
            "elevated broker is up"
            if live.get("ok")
            else (
                "Full-Trust will auto-start the broker (one UAC) on the first admin op"
                if should_escalate()
                else "broker idle — Full-Trust + first privileged op starts it"
            )
        ),
    }


def _run_cmd(cmd: Any, timeout: float = 60.0) -> Dict[str, Any]:
    if isinstance(cmd, str):
        argv: Sequence[str] = cmd
        shell = True
    elif isinstance(cmd, (list, tuple)):
        argv = [str(x) for x in cmd]
        shell = False
    else:
        return {"ok": False, "error": "run_cmd requires argv list or string"}
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=float(timeout),
            shell=shell,
            check=False,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "stdout": (completed.stdout or "")[:8000],
        "stderr": (completed.stderr or "")[:4000],
        "error": None if completed.returncode == 0 else ((completed.stderr or completed.stdout or "exit").strip()[:400]),
    }


def dispatch(op: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Run an op locally (used by the broker, and by tests)."""
    p = dict(payload or {})
    name = (op or "").strip()
    if name in {"ping", "status"}:
        return {"ok": True, "pong": True, "admin": is_admin(), "pid": os.getpid()}
    if name == "registry_write":
        from exo_control import registry_ops

        return registry_ops.registry_write(
            str(p.get("path") or ""),
            str(p.get("name") or ""),
            p.get("value"),
            value_type=str(p.get("value_type") or "string"),
            confirm=True,
        )
    if name == "registry_delete":
        from exo_control import registry_ops

        return registry_ops.registry_delete(
            str(p.get("path") or ""),
            name=p.get("name"),
            recursive=bool(p.get("recursive", False)),
            confirm=True,
        )
    if name == "files_write":
        from exo_control import files_ops

        return files_ops.files_write(str(p.get("path") or ""), str(p.get("text") or ""), confirm=True)
    if name == "files_delete":
        from exo_control import files_ops

        return files_ops.files_delete(
            str(p.get("path") or ""),
            confirm=True,
            recursive=bool(p.get("recursive", False)),
        )
    if name == "files_copy":
        from exo_control import files_ops

        return files_ops.files_copy(src=str(p.get("src") or ""), dst=str(p.get("dst") or ""), confirm=True)
    if name == "files_move":
        from exo_control import files_ops

        return files_ops.files_move(src=str(p.get("src") or ""), dst=str(p.get("dst") or ""), confirm=True)
    if name == "files_mkdir":
        from exo_control.os_ops import files_mkdir

        return files_mkdir(str(p.get("path") or ""), confirm=True)
    if name == "kill_proc":
        from exo_control import infra_ops

        pid = p.get("pid")
        return infra_ops.kill_proc(
            int(pid) if pid is not None else None,
            name=p.get("name"),
            confirm=True,
        )
    if name == "service_control":
        from exo_control import infra_ops

        return infra_ops.service_control(str(p.get("name") or ""), str(p.get("action") or ""), confirm=True)
    if name in {"run_cmd", "run_elevated"}:
        return _run_cmd(p.get("argv") if p.get("argv") is not None else p.get("cmd"), timeout=float(p.get("timeout") or 60))
    return {"ok": False, "error": f"unknown elevate op: {name}"}


def call(op: str, payload: Optional[Dict[str, Any]] = None, *, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    ready = ensure_broker(uac=True)
    if not ready.get("ok"):
        return ready
    ep = read_endpoint()
    if not ep:
        return {"ok": False, "error": "elevate_broker_offline"}
    out = _rpc({"token": ep["token"], "op": op, "payload": dict(payload or {})}, timeout=timeout)
    if isinstance(out, dict):
        out.setdefault("elevated", True)
    return out


def retry_if_needed(op: str, result: Dict[str, Any], payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not isinstance(result, dict) or result.get("ok"):
        return result
    if not should_escalate():
        return result
    if not looks_access_denied(result) and op not in {
        "registry_write",
        "registry_delete",
        "service_control",
        "run_cmd",
        "run_elevated",
    }:
        return result
    from exo_control.trust import audit_append

    audit_append("elevate_retry", op=op, reason=str(result.get("error") or "")[:200])
    return call(op, payload)


def handle_request(req: Dict[str, Any], token: str) -> Dict[str, Any]:
    from exo_control.trust import human_kill_armed, kill_file_present

    if human_kill_armed():
        kill = kill_file_present()
        return {
            "ok": False,
            "error": "kill_switch",
            "path": str(kill) if kill else None,
        }
    if not secrets.compare_digest(str(req.get("token") or ""), str(token)):
        return {"ok": False, "error": "elevate_bad_token"}
    return dispatch(str(req.get("op") or ""), req.get("payload") if isinstance(req.get("payload"), dict) else {})


def serve_forever() -> int:
    """Listen on 127.0.0.1. Called by the elevated helper process only."""
    os.environ["EXO_ELEVATED_BROKER"] = "1"
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(16)
    port = int(sock.getsockname()[1])
    token = secrets.token_hex(32)
    write_endpoint(port=port, token=token, pid=os.getpid())
    from exo_control.trust import audit_append

    audit_append("elevate_broker_listen", port=port, pid=os.getpid(), admin=is_admin())
    try:
        while True:
            conn, _addr = sock.accept()
            try:
                chunks: List[bytes] = []
                conn.settimeout(30.0)
                while True:
                    buf = conn.recv(65536)
                    if not buf:
                        break
                    chunks.append(buf)
                    if b"\n" in buf:
                        break
                raw = b"".join(chunks).decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    req = json.loads(raw.splitlines()[0])
                except json.JSONDecodeError:
                    resp = {"ok": False, "error": "elevate_bad_json"}
                else:
                    resp = handle_request(req if isinstance(req, dict) else {}, token)
                conn.sendall((json.dumps(resp, ensure_ascii=False, default=str) + "\n").encode("utf-8"))
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except Exception:
                    pass
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            sock.close()
        except Exception:
            pass
        try:
            endpoint_path().unlink(missing_ok=True)
        except OSError:
            pass
    return 0
