"""Where the e2e scripts get a *template* project from.

They never touch a real project in place: a template is copied into ``sandbox/<name>`` and all
writes happen there.  Point ``AUTOSHOPKIT_TEMPLATE`` at any saved ``.hcp`` project (or drop one
into ``sandbox/template``) — the scripts skip with a clear message when it is absent.
"""
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SANDBOX = os.path.join(ROOT, "sandbox")


def template_dir():
    """Directory holding the template project, or ``None``."""
    candidate = os.environ.get("AUTOSHOPKIT_TEMPLATE", "").strip()
    if candidate and os.path.isdir(candidate):
        return candidate
    local = os.path.join(SANDBOX, "template")
    return local if os.path.isdir(local) else None


def require_template(script):
    """Print a SKIP notice and return ``None`` when no template is configured."""
    directory = template_dir()
    if directory is None:
        print("[SKIP] %s: 没有模板工程，设 AUTOSHOPKIT_TEMPLATE=<工程目录> 后重跑" % script)
    return directory


def fresh_copy(name, script):
    """Copy the template into ``sandbox/<name>`` and return the new directory."""
    directory = require_template(script)
    if directory is None:
        return None
    target = os.path.join(SANDBOX, name)
    if os.path.isdir(target):
        shutil.rmtree(target)
    shutil.copytree(directory, target)
    return target
