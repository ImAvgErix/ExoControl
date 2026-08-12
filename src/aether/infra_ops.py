"""OS infrastructure ops: processes, services, env, tasks, startup."""
from __future__ import annotations

import csv
import io
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

# Anti-cheat / protected process name substrings (case-insensitive).
PROTECTED_PROCESS_SUBSTR = (
    "easyanticheat",
    "battleye",
    "vgc",
    "vgtray",
    "faceit",
    "ricochet",
)


def _run(cmd: List[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        creationflags=creationflags,
    )


def proc_list(max_items: int = 120) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": True, "procs": [], "note": "proc list is Windows-oriented"}
    try:
        completed = _run(["tasklist", "/FO", "CSV", "/NH"], timeout=10)
        rows: List[Dict[str, Any]] = []
        reader = csv.reader(io.StringIO(completed.stdout or ""))
        for row in reader:
            if len(row) < 2:
                continue
            name, pid_s = row[0], row[1]
            try:
                pid = int(pid_s)
            except ValueError:
                continue
            rows.append({"pid": pid, "name": name})
            if len(rows) >= max_items:
                break
        return {"ok": True, "procs": rows, "count": len(rows)}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def _proc_name_for_pid(pid: int) -> str:
    if os.name != "nt" or pid <= 0:
        return ""
    try:
        completed = _run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], timeout=8)
        reader = csv.reader(io.StringIO(completed.stdout or ""))
        for row in reader:
            if len(row) >= 2:
                return str(row[0] or "")
    except Exception:
        pass
    return ""


def is_protected_process(name: str) -> bool:
    low = (name or "").lower()
    return any(s in low for s in PROTECTED_PROCESS_SUBSTR)


def find_pids_by_name(name: str, max_hits: int = 20) -> List[Dict[str, Any]]:
    """Resolve running process rows whose name contains ``name`` (case-insensitive)."""
    needle = (name or "").strip().lower()
    if not needle:
        return []
    listed = proc_list(max_items=500)
    hits: List[Dict[str, Any]] = []
    for row in listed.get("procs") or []:
        pname = str(row.get("name") or "")
        if needle in pname.lower():
            hits.append({"pid": int(row.get("pid") or 0), "name": pname})
            if len(hits) >= max_hits:
                break
    return hits


def kill_proc(
    pid: Optional[int] = None,
    *,
    name: Optional[str] = None,
    confirm: bool = False,
) -> Dict[str, Any]:
    """Kill by pid and/or process name.

    Name-only path hard-denies protected anti-cheat substrings without requiring
    a pid (agents must not need a handle on something they cannot kill).
    """
    if not confirm:
        return {"ok": False, "error": "proc kill requires confirm=true"}

    name_s = (name or "").strip()
    if name_s and is_protected_process(name_s):
        return {
            "ok": False,
            "error": "protected_process",
            "reason": "protected_process",
            "name": name_s,
            "denied": True,
        }

    targets: List[Dict[str, Any]] = []
    if pid is not None:
        try:
            pid_i = int(pid)
        except (TypeError, ValueError):
            return {"ok": False, "error": "invalid pid"}
        if pid_i <= 0:
            return {"ok": False, "error": "invalid pid"}
        pname = _proc_name_for_pid(pid_i)
        if pname and is_protected_process(pname):
            return {
                "ok": False,
                "error": "protected_process",
                "reason": "protected_process",
                "pid": pid_i,
                "name": pname,
                "denied": True,
            }
        targets.append({"pid": pid_i, "name": pname})
    elif name_s:
        targets = find_pids_by_name(name_s)
        if not targets:
            return {"ok": False, "error": "no matching process", "name": name_s}
        # Re-check resolved names (list may lag; still deny if any protected).
        for t in targets:
            if is_protected_process(str(t.get("name") or "")):
                return {
                    "ok": False,
                    "error": "protected_process",
                    "reason": "protected_process",
                    "pid": t.get("pid"),
                    "name": t.get("name"),
                    "denied": True,
                }
    else:
        return {"ok": False, "error": "proc kill requires pid or name"}

    results: List[Dict[str, Any]] = []
    all_ok = True
    for t in targets:
        tpid = int(t["pid"])
        tname = str(t.get("name") or "")
        try:
            if os.name == "nt":
                completed = _run(["taskkill", "/PID", str(tpid), "/T", "/F"], timeout=10)
                ok = completed.returncode == 0
                results.append({
                    "ok": ok,
                    "pid": tpid,
                    "name": tname,
                    "stdout": (completed.stdout or "").strip()[:300],
                    "stderr": (completed.stderr or "").strip()[:300],
                })
                all_ok = all_ok and ok
            else:
                os.kill(tpid, 9)
                results.append({"ok": True, "pid": tpid, "name": tname})
        except Exception as exc:
            all_ok = False
            results.append({
                "ok": False,
                "pid": tpid,
                "name": tname,
                "error": f"{type(exc).__name__}: {exc}",
            })

    if len(results) == 1:
        return results[0]
    return {
        "ok": all_ok,
        "killed": [r for r in results if r.get("ok")],
        "failed": [r for r in results if not r.get("ok")],
        "count": len(results),
        "name": name_s or None,
    }


def service_list(max_items: int = 80) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "services require Windows"}
    try:
        completed = _run(["sc", "query", "state=", "all"], timeout=20)
        services: List[Dict[str, Any]] = []
        name = None
        for line in (completed.stdout or "").splitlines():
            line = line.strip()
            if not line:
                continue
            upper = line.upper()
            # sc pads keys: "STATE              : 4  RUNNING"
            if upper.startswith("SERVICE_NAME") and ":" in line:
                name = line.split(":", 1)[1].strip()
            elif upper.startswith("STATE") and ":" in line and name:
                parts = line.split(":", 1)[1].strip().split()
                state = parts[-1] if parts else ""
                services.append({"name": name, "state": state})
                name = None
                if len(services) >= max_items:
                    break
        if not services:
            # Fallback when sc output locale/format differs
            ps = _run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Get-Service | Select-Object -First {int(max_items)} Name,Status | ConvertTo-Csv -NoTypeInformation",
                ],
                timeout=25,
            )
            import csv
            import io
            for row in csv.DictReader(io.StringIO(ps.stdout or "")):
                n = (row.get("Name") or "").strip()
                st = (row.get("Status") or "").strip()
                if n:
                    services.append({"name": n, "state": st})
        return {
            "ok": True,
            "services": services,
            "count": len(services),
            "capped": len(services) >= max_items,
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def service_status(name: str) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "services require Windows"}
    name = (name or "").strip()
    if not name:
        return {"ok": False, "error": "service name required"}
    try:
        completed = _run(["sc", "query", name], timeout=12)
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        if completed.returncode != 0:
            msg = err or out or f"sc exit {completed.returncode}"
            return {"ok": False, "error": msg[:400], "name": name}
        state = ""
        for line in out.splitlines():
            if line.strip().upper().startswith("STATE"):
                parts = line.split(":", 1)[1].strip().split()
                state = parts[-1] if parts else ""
        return {"ok": True, "name": name, "state": state, "raw": out[:500]}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "name": name}


def service_control(name: str, action: str, *, confirm: bool = False) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "services require Windows"}
    if not confirm:
        return {"ok": False, "error": "service_control requires confirm=true"}
    name = (name or "").strip()
    action = (action or "").strip().lower()
    if not name:
        return {"ok": False, "error": "service name required"}
    if action not in {"start", "stop", "restart"}:
        return {"ok": False, "error": f"unsupported action: {action}"}
    try:
        if action == "restart":
            _run(["sc", "stop", name], timeout=20)
            completed = _run(["sc", "start", name], timeout=20)
        else:
            completed = _run(["sc", action, name], timeout=20)
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        ok = completed.returncode == 0
        return {
            "ok": ok,
            "name": name,
            "action": action,
            "stdout": out[:400],
            "stderr": err[:400],
            "error": None if ok else (err or out or f"sc exit {completed.returncode}")[:400],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "name": name, "action": action}


def env_get(name: Optional[str] = None) -> Dict[str, Any]:
    if name:
        if name not in os.environ:
            return {"ok": False, "error": "env var not set", "name": name}
        val = os.environ.get(name, "")
        if len(val) > 2000:
            val = val[:1997] + "..."
        return {"ok": True, "name": name, "value": val}
    # names only
    names = sorted(os.environ.keys())[:200]
    return {"ok": True, "names": names, "count": len(names)}


def env_list(max_items: int = 200) -> Dict[str, Any]:
    names = sorted(os.environ.keys())[:max_items]
    return {"ok": True, "names": names, "count": len(names), "capped": len(os.environ) > max_items}


def tasks_list(max_items: int = 40) -> Dict[str, Any]:
    if os.name != "nt":
        return {"ok": False, "error": "tasks_list requires Windows"}
    try:
        completed = _run(["schtasks", "/Query", "/FO", "CSV", "/NH"], timeout=20)
        rows: List[Dict[str, Any]] = []
        reader = csv.reader(io.StringIO(completed.stdout or ""))
        for row in reader:
            if not row:
                continue
            # TaskName, Next Run Time, Status
            item = {
                "name": row[0] if len(row) > 0 else "",
                "next_run": row[1] if len(row) > 1 else "",
                "status": row[2] if len(row) > 2 else "",
            }
            if item["name"]:
                rows.append(item)
            if len(rows) >= max_items:
                break
        return {"ok": True, "tasks": rows, "count": len(rows), "capped": len(rows) >= max_items}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def startup_list(max_items: int = 80) -> Dict[str, Any]:
    candidates = []
    appdata = os.environ.get("APPDATA")
    progdata = os.environ.get("PROGRAMDATA")
    if appdata:
        candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup")
    if progdata:
        candidates.append(Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "StartUp")
    items: List[Dict[str, Any]] = []
    for folder in candidates:
        if not folder.exists():
            continue
        try:
            for entry in folder.iterdir():
                items.append({
                    "name": entry.name,
                    "path": str(entry),
                    "scope": "user" if appdata and str(folder).startswith(appdata) else "common",
                    "is_dir": entry.is_dir(),
                })
                if len(items) >= max_items:
                    break
        except OSError:
            continue
        if len(items) >= max_items:
            break
    return {"ok": True, "items": items, "count": len(items), "capped": len(items) >= max_items}
