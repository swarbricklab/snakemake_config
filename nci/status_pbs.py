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
was and the answer is `running`. A failure also records the memory and walltime the job
spent against what it asked for, because a PBS memory kill ends the process and not the
job, so nothing else distinguishes it from a code error. Events go to `status.log` in the
cache directory.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

STATE_FILE = "state.json"
LOCK_FILE = "lock"
LOG_FILE = "status.log"

#: PBS size suffixes, which are binary multiples.
SIZE_UNITS = {"b": 1, "kb": 1024, "mb": 1024**2, "gb": 1024**3, "tb": 1024**4}
SIZE_PATTERN = re.compile(r"(\d+)(b|kb|mb|gb|tb)?\Z")
#: How close to its request a job must come for the note to call it a limit.
AT_LIMIT_FRACTION = 0.98
GIB = 1024**3


def parse_size(value: object) -> int | None:
    """Parse a PBS size such as `8388608000b` or `8192000kb` into bytes."""
    match = SIZE_PATTERN.match(str(value or "").strip().lower())
    return int(match.group(1)) * SIZE_UNITS[match.group(2) or "b"] if match else None


def parse_walltime(value: object) -> int | None:
    """Parse a PBS walltime `H:MM:SS` into seconds."""
    parts = str(value or "").strip().split(":")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    hours, minutes, seconds = (int(part) for part in parts)
    return hours * 3600 + minutes * 60 + seconds


def limit_note(entry: dict) -> str:
    """Say which request a failed job spent, so a limit kill is not read as a code error.

    A PBS memory kill ends the process, not the job, so the job's status is its last
    command's: a rule that ran out of memory looks like any other failure everywhere except
    in the numbers PBS records. Measured on Gadi 2026-09-16, a conform job used exactly the
    8000 MB it asked for and its container exited 137, while the job reported `Exit_status`
    1. Reading the request back is what turns that into a resources row to raise.
    """
    used_mem, asked_mem = parse_size(entry.get("used_mem")), parse_size(entry.get("asked_mem"))
    used_time = parse_walltime(entry.get("used_walltime"))
    asked_time = parse_walltime(entry.get("asked_walltime"))
    notes = []
    if used_mem is not None and asked_mem:
        spent = f"memory {used_mem / GIB:.2f} GB of {asked_mem / GIB:.2f} GB requested"
        at_limit = used_mem >= asked_mem * AT_LIMIT_FRACTION
        notes.append(f"{spent}, at its limit: raise the rule's mem_mb" if at_limit else spent)
    if used_time is not None and asked_time:
        spent = f"walltime {used_time} s of {asked_time} s requested"
        at_limit = used_time >= asked_time * AT_LIMIT_FRACTION
        notes.append(f"{spent}, at its limit: raise the rule's runtime_min" if at_limit else spent)
    return "; ".join(notes)


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
        asked = job.get("Resource_List") or {}
        used = job.get("resources_used") or {}
        reported[_numeric(key)] = {
            "state": job.get("job_state"),
            "exit": job.get("Exit_status"),
            "comment": job.get("comment"),
            "asked_mem": asked.get("mem"),
            "used_mem": used.get("mem"),
            "asked_walltime": asked.get("walltime"),
            "used_walltime": used.get("walltime"),
        }
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
        spent = limit_note(entry)
        _log(
            log_path,
            f"{jobid} finished with exit {code}{note}: failed"
            + (f"; {spent}" if spent else ""),
        )
        return "failed"
    if job_state == "unknown":
        _log(
            log_path,
            f"{jobid} is unknown to qstat (finished more than 24 h ago, or never existed): failed",
        )
        return "failed"
    if job_state == "H" and not entry.get("held_logged"):
        # PBS puts the reason in `comment`, and it is usually the whole diagnosis: an
        # operator hold reading "Project a56 is over storage allocation on gadi-scratch1"
        # holds every job of the project until someone frees space (seen 2026-09-16).
        reason = str(entry.get("comment") or "no reason given by qstat")
        _log(
            log_path,
            f"{jobid} is held (H): {reason}; it stays running for Snakemake, so the run "
            "waits until the hold clears",
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
