"""Long-running supervisor (directive §28).

Light watchdog: reads automation/TASK_STATE.json, checks whether the
expected workers (forever trainer, qa runner, app server) are alive, logs
restart attempts, restarts stopped workers, and prints the continuation
message. It stays within what this environment actually allows: it can
spawn/restart local processes; it cannot post into an agent chat, so it
emits the continuation instruction on stdout for whoever reads the log.

  PYTHONPATH=vendor:app/deps:. python3 automation/timer.py [interval_sec]
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "automation/TASK_STATE.json"
LOG = ROOT / "automation/supervisor.log"
COMPLETION_GOALS = {"images": 70_000, "steps": 2_000_000}

CONT = "CONTINUE FROM TASK_STATE.JSON. DO NOT DECLARE COMPLETE. EXECUTE THE NEXT PENDING BATCH AND UPDATE THE CHECKPOINT."


def sh(cmd: str, **kw):
    return subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=20, **kw)


def alive(pattern: str) -> bool:
    return pattern in sh("pgrep -af " + pattern).stdout or bool(sh("pgrep -f " + pattern).stdout.strip())


def server_ok() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/healthz", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def read_state() -> dict:
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def read_pretrain_progress() -> dict:
    try:
        return json.loads((ROOT / "model/out/pretrain_progress.json").read_text())
    except Exception:
        return {}


def main() -> None:
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log("supervisor start; interval=%ss goals=%s" % (interval, COMPLETION_GOALS))
    restarts = 0
    while True:
        st = read_state()
        prog = read_pretrain_progress()
        steps = st.get("last_train_steps") or prog.get("steps_total", 0) or 0
        imgs = st.get("dataset_count") or 0
        done = steps >= COMPLETION_GOALS["steps"] and (imgs == 0 or imgs >= COMPLETION_GOALS["images"])
        if done:
            log("completion criteria reached (steps=%s imgs=%s). supervisor exits." % (steps, imgs))
            return
        if not server_ok():
            log("app server DOWN -> restart via scripts/start-preview.sh")
            subprocess.Popen(["bash", str(ROOT / "scripts/start-preview.sh")], cwd=ROOT,
                             stdout=open("/tmp/sv-website.log", "ab"), stderr=subprocess.STDOUT)
            restarts += 1
        if not alive("model.forever_train"):
            log("forever trainer DOWN -> relaunch")
            subprocess.Popen(f"cd {ROOT} && PYTHONPATH=app/deps:vendor:. python3 -m model.forever_train",
                             shell=True, stdout=open("/tmp/sv-train.log", "ab"), stderr=subprocess.STDOUT)
            restarts += 1
        if not alive("qa.runner") and st.get("current_phase") == "qa_runner":
            todo = st.get("remaining_cases", 0)
            if todo:
                log(f"qa runner DOWN with {todo} cases left -> relaunch")
                subprocess.Popen(f"cd {ROOT} && PYTHONPATH=app/deps:vendor:. python3 qa/runner.py",
                                 shell=True, stdout=open("/tmp/sv-qa.log", "ab"), stderr=subprocess.STDOUT)
                restarts += 1
        log(f"state: phase={st.get('current_phase')} steps={steps} restarts_total={restarts}")
        print(CONT, flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()
