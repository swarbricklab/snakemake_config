#!/usr/bin/env python3
"""Report one PBS job's state to Snakemake as exactly one of running, success, or failed.

Snakemake's cluster-generic executor runs `status_pbs.py JOBID` for every active job on
each polling round. To spare the scheduler, this script asks `qstat` about all the jobs
it is watching in one call, at most once per `--interval` seconds, and answers the other
calls from that cache (`.snakemake/pbs_status/` under the working directory). It never
exits non-zero and never prints a second line, because either aborts the whole workflow.

Answers: a queued, running, held, suspended, or exiting job is `running` (a held job is
logged once); a finished job is `success` when its `Exit_status` is 0 and `failed`
otherwise (a negative status is a PBS kill, `-29` the walltime limit); a job that `qstat`
no longer knows, which happens 24 hours after it finished, is `failed`, so Snakemake redoes
it instead of waiting forever; a `qstat` that fails or times out leaves the cache as it
was and the answer is `running`. Events go to `status.log` in the cache directory.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

STATE_FILE = "state.json"
LOCK_FILE = "lock"
LOG_FILE = "status.log"


def _numeric(jobid: str) -> str:
    """`179107526.gadi-pbs` and `179107526` name the same job."""
    return jobid.split(".", 1)[0]


def _log(log_path: Path, message: str) -> None:
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {message}\n")


def _load(state_path: Path, log_path: Path) -> dict:
    if not state_path.exists():
        return {"checked": 0.0, "jobs": {}, "pending": []}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _log(log_path, f"state file unreadable ({error}); starting a fresh cache")
        return {"checked": 0.0, "jobs": {}, "pending": []}


def _save(state_path: Path, state: dict) -> None:
    temporary = state_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(state_path)


def refresh(state: dict, *, qstat: str, timeout: float, log_path: Path, now: float) -> None:
    """Ask qstat about every pending job in one call and rewrite the cached states."""
    state["checked"] = now
    pending = list(state.get("pending") or [])
    if not pending:
        return
    command = [*shlex.split(qstat), "-x", "-f", "-F", "json", *pending]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as error:
        _log(log_path, f"qstat unavailable ({error}); keeping the previous answers")
        return
    try:
        document = json.loads(completed.stdout)
    except json.JSONDecodeError:
        _log(
            log_path,
            f"qstat exit {completed.returncode} without JSON output; keeping the previous "
            f"answers: {completed.stderr.strip()[:200]}",
        )
        return
    if completed.returncode != 0:
        _log(
            log_path,
            f"qstat exit {completed.returncode} with JSON output: "
            f"{completed.stderr.strip()[:200]}",
        )
    reported = {}
    for key, job in (document.get("Jobs") or {}).items():
        reported[_numeric(key)] = {"state": job.get("job_state"), "exit": job.get("Exit_status")}
    jobs = state.setdefault("jobs", {})
    for jobid in pending:
        entry = reported.get(_numeric(jobid)) or {"state": "unknown"}
        entry["held_logged"] = bool(jobs.get(jobid, {}).get("held_logged"))
        jobs[jobid] = entry


def answer(state: dict, jobid: str, log_path: Path) -> str:
    """Classify one job from the cache: running, success, or failed."""
    entry = state.get("jobs", {}).get(jobid)
    if entry is None:
        return "running"  # newer than the last qstat call; the next refresh covers it
    job_state = entry.get("state")
    if job_state == "F":
        code = entry.get("exit")
        if code == 0:
            _log(log_path, f"{jobid} finished with exit 0: success")
            return "success"
        note = (
            " (killed by PBS; -29 is the walltime limit)"
            if isinstance(code, int) and code < 0
            else ""
        )
        _log(log_path, f"{jobid} finished with exit {code}{note}: failed")
        return "failed"
    if job_state == "unknown":
        _log(
            log_path,
            f"{jobid} is unknown to qstat (finished more than 24 h ago, or never existed): failed",
        )
        return "failed"
    if job_state == "H" and not entry.get("held_logged"):
        _log(
            log_path,
            f"{jobid} is held (H); check the project's quota and the request; "
            "it stays running for Snakemake",
        )
        entry["held_logged"] = True
    return "running"


def main(argv: list[str]) -> int:
    """Answer for one job, refreshing the shared cache when its interval has passed."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("jobid", help="the PBS job id the submit command printed")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".snakemake") / "pbs_status",
        help="where the shared cache and status.log live (default: .snakemake/pbs_status)",
    )
    parser.add_argument(
        "--interval", type=float, default=60.0, help="seconds between qstat calls (default: 60)"
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="seconds to wait for qstat before giving up this round (default: 60)",
    )
    parser.add_argument(
        "--qstat", default="qstat", help="the qstat command (tests substitute a fake)"
    )
    args = parser.parse_args(argv)

    cache = args.cache_dir
    cache.mkdir(parents=True, exist_ok=True)
    log_path = cache / LOG_FILE
    with (cache / LOCK_FILE).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = _load(cache / STATE_FILE, log_path)
        pending = state.setdefault("pending", [])
        if args.jobid not in pending:
            pending.append(args.jobid)
        now = time.time()
        if now - float(state.get("checked") or 0.0) >= args.interval:
            refresh(state, qstat=args.qstat, timeout=args.timeout, log_path=log_path, now=now)
        result = answer(state, args.jobid, log_path)
        if result != "running":
            state["pending"] = [jobid for jobid in pending if jobid != args.jobid]
            state.get("jobs", {}).pop(args.jobid, None)
        _save(cache / STATE_FILE, state)
    print(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as error:  # any other failure must still answer Snakemake
        print(f"status_pbs: {error!r}; answering running", file=sys.stderr)
        print("running")
        sys.exit(0)
