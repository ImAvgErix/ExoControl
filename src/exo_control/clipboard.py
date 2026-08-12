
"""Clipboard helpers (cross-platform best-effort)."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Tuple


def get_clipboard() -> Tuple[bool, str]:
    try:
        import pyperclip
        return True, pyperclip.paste() or ""
    except Exception:
        pass
    try:
        from tkinter import Tk
        r = Tk()
        r.withdraw()
        text = r.clipboard_get()
        r.destroy()
        return True, text
    except Exception as e:
        return False, str(e)


def set_clipboard(text: str) -> Tuple[bool, str]:
    try:
        import pyperclip
        pyperclip.copy(text)
        return True, "ok"
    except Exception:
        pass
    try:
        from tkinter import Tk
        r = Tk()
        r.withdraw()
        r.clipboard_clear()
        r.clipboard_append(text)
        r.update()
        r.destroy()
        return True, "ok"
    except Exception as e:
        return False, str(e)


def set_clipboard_image(path: str) -> Dict[str, Any]:
    """Put an image file (PNG/JPEG/BMP/…) onto the system clipboard."""
    import os
    import subprocess
    p = Path(path)
    if not p.is_file():
        return {"ok": False, "error": f"file not found: {path}"}

    # Prefer Pillow + win32clipboard when available (fast, in-process).
    if os.name == "nt":
        try:
            from PIL import Image
            import io
            img = Image.open(str(p)).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, "BMP")
            dib = buf.getvalue()[14:]  # CF_DIB = BMP without file header
            try:
                import win32clipboard  # type: ignore
                win32clipboard.OpenClipboard()
                try:
                    win32clipboard.EmptyClipboard()
                    win32clipboard.SetClipboardData(win32clipboard.CF_DIB, dib)
                finally:
                    win32clipboard.CloseClipboard()
                return {"ok": True, "path": str(p.resolve()), "size": list(img.size), "method": "win32clipboard"}
            except Exception:
                pass
        except Exception as exc:
            win32_err = f"{type(exc).__name__}: {exc}"
        else:
            win32_err = "win32clipboard unavailable"
        # PowerShell / WinForms fallback
        ps_path = str(p.resolve()).replace("'", "''")
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            f"$img = [System.Drawing.Image]::FromFile('{ps_path}'); "
            "[System.Windows.Forms.Clipboard]::SetImage($img); "
            "$img.Dispose(); "
            "Write-Output 'ok'"
        )
        try:
            creationflags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True, text=True, timeout=30, creationflags=creationflags,
            )
            if proc.returncode == 0 and "ok" in (proc.stdout or ""):
                return {"ok": True, "path": str(p.resolve()), "method": "powershell"}
            return {
                "ok": False,
                "error": (proc.stderr or proc.stdout or "powershell clipboard set failed").strip()
                or win32_err,
            }
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}; prior={win32_err}"}

    # Non-Windows: best-effort via PIL + pbcopy/xclip not standardized for images.
    return {"ok": False, "error": "clipboard image set is Windows-only"}
