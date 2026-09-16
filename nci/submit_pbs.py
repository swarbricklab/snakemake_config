#!/usr/bin/env python3
"""Submit one Snakemake job to PBS Pro on Gadi, on the cheapest queue that fits it.

Snakemake's cluster-generic executor runs this as the submit command, appending the
jobscript path:

    submit_pbs.py [--project P] [--storage LIST] [--pass-env A,B] [--queues FILE] JOBSCRIPT

The jobscript's `# properties = {...}` line carries the rule name, Snakemake's `threads`,
and the resources in Snakemake's own vocabulary: `mem_mb`, `runtime` (minutes), `disk_mb`,
and optionally `gpus` and `queue`. Nothing here belongs to one workflow; the site facts
live in `queues.yaml` beside this file and in the options the profile passes.

Queue choice minimizes the charge per hour over the enabled rows of the table, among the
rows the job fits (memory, cores, walltime, jobfs, GPUs). The request asks for `threads`
cores raised to the queue's minimum, the memory as declared, the walltime from `runtime`,
and jobfs from `disk_mb`. A queue whose memory floor the request does not meet is not a
fit: NCI's floors say which jobs belong on the large-memory nodes, and inflating a request
to reach a cheaper rate would occupy those nodes and send most jobs to a small queue.
Cores that the memory share already pays for are not requested either: the charge is the
same and a smaller request schedules sooner.

The PBS log (stdout and stderr joined) goes to a `pbs/` directory beside the job's first
declared log, named after that log with the submission time appended, so every attempt
keeps its own file: `logs/<cohort>/<stage>/pbs/<rule>.<wildcards>.<stamp>.log` in
seamark's layout, or `logs/pbs/<rule>.<jobid>.<stamp>.log` for a rule without a log.

The environment is never exported wholesale (no `qsub -V`); `--pass-env` names the
variables a job needs and `qsub -v NAME` copies each from this process. The PBS job id
goes to stdout; a refused submission exits with qsub's code and its message on stderr.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

PROPERTIES_PREFIX = "# properties = "
MINIMUM_JOBFS_MB = 100
ROW_KEYS = (
    "enabled",
    "su_per_core_hour",
    "cores_per_node",
    "mem_per_node_gb",
    "max_mem_gb",
    "min_mem_gb",
    "min_ncpus",
    "max_ncpus",
    "max_walltime_hours",
    "max_jobfs_gb",
    "gpus",
)


class SubmitError(Exception):
    """A request that cannot be submitted; the message names the fix."""


@dataclass(frozen=True)
class Allocation:
    """What the job asks PBS for, and what that costs per hour."""

    queue: str
    ncpus: int
    ngpus: int
    mem_mb: int
    walltime_seconds: int
    jobfs_mb: int
    su_per_hour: float

    @property
    def walltime(self) -> str:
        """The walltime as PBS writes it, `H:MM:SS`."""
        hours, rest = divmod(self.walltime_seconds, 3600)
        minutes, seconds = divmod(rest, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}"


def read_job_properties(jobscript: Path) -> dict:
    """Return the JSON object Snakemake wrote on the jobscript's `# properties = ` line."""
    for line in jobscript.read_text(encoding="utf-8").splitlines():
        if line.startswith(PROPERTIES_PREFIX):
            return json.loads(line[len(PROPERTIES_PREFIX) :])
    raise SubmitError(
        f"{jobscript} has no '{PROPERTIES_PREFIX.strip()}' line; is it a Snakemake jobscript?"
    )


def load_queue_table(path: Path) -> dict[str, dict]:
    """Read `queues.yaml` and check every row carries the keys the allocation reads."""
    try:
        # PyYAML directly: this script imports nothing from any workflow.
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as error:
        raise SubmitError(f"cannot read the queue table {path}: {error}") from error
    table = document.get("queues")
    if not isinstance(table, dict) or not table:
        raise SubmitError(f"{path} has no `queues:` mapping")
    for name, row in table.items():
        missing = [key for key in ROW_KEYS if key not in row]
        if missing:
            raise SubmitError(f"queue {name!r} in {path} lacks {missing}")
        if row["gpus"] and "ncpus_per_gpu" not in row:
            raise SubmitError(f"GPU queue {name!r} in {path} lacks ncpus_per_gpu")
    return table


def _cores(row: dict, threads: int, gpus: int) -> tuple[int, int]:
    """Return (ncpus, ngpus) for one row: threads raised to its minimum, GPUs in whole units."""
    ncpus = max(threads, int(row["min_ncpus"]))
    if not row["gpus"]:
        return ncpus, 0
    per_gpu = int(row["ncpus_per_gpu"])
    ngpus = max(gpus, math.ceil(ncpus / per_gpu))
    return per_gpu * ngpus, ngpus


def _misfit(
    row: dict, *, threads: int, mem_mb: int, runtime_min: float, disk_mb: int, gpus: int
) -> str | None:
    """Return why the job does not fit the row, or None when it does."""
    if gpus and not row["gpus"]:
        return "no GPUs"
    if row["gpus"] and not gpus:
        return "a GPU queue needs a gpus request"
    mem_gb = mem_mb / 1024
    if mem_gb > float(row["max_mem_gb"]):
        return f"memory {mem_gb:g} GB above its {row['max_mem_gb']} GB"
    if mem_gb < float(row["min_mem_gb"]):
        return f"memory {mem_gb:g} GB below its {row['min_mem_gb']} GB floor"
    ncpus, _ = _cores(row, threads, gpus)
    if ncpus > int(row["max_ncpus"]):
        return f"{ncpus} cores above its {row['max_ncpus']}"
    if runtime_min / 60 > float(row["max_walltime_hours"]):
        return f"walltime {runtime_min / 60:g} h above its {row['max_walltime_hours']} h"
    if disk_mb / 1024 > float(row["max_jobfs_gb"]):
        return f"jobfs {disk_mb / 1024:g} GB above its {row['max_jobfs_gb']} GB"
    return None


def _allocation(
    name: str, row: dict, *, threads: int, mem_mb: int, runtime_min: float, disk_mb: int, gpus: int
) -> Allocation:
    """Build the request for one fitting row and price it with Gadi's charge formula."""
    ncpus, ngpus = _cores(row, threads, gpus)
    memory_share = mem_mb / 1024 / float(row["mem_per_node_gb"]) * int(row["cores_per_node"])
    su_per_hour = float(row["su_per_core_hour"]) * max(ncpus, memory_share)
    return Allocation(
        queue=name,
        ncpus=ncpus,
        ngpus=ngpus,
        mem_mb=mem_mb,
        walltime_seconds=math.ceil(runtime_min * 60),
        jobfs_mb=max(disk_mb, MINIMUM_JOBFS_MB),
        su_per_hour=su_per_hour,
    )


def _required(resources: dict, key: str, rule: str) -> float:
    value = resources.get(key)
    if value is None:
        raise SubmitError(
            f"rule {rule!r} declares no `{key}` resource; fix: set it in the rule or in the "
            "profile's default-resources"
        )
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise SubmitError(
            f"rule {rule!r} has a non-numeric `{key}` resource: {value!r}"
        ) from error


def allocate(properties: dict, table: dict[str, dict]) -> Allocation:
    """Choose the cheapest enabled queue the job fits, or the requested one; size the request."""
    resources = properties.get("resources") or {}
    rule = properties.get("rule") or properties.get("groupid") or "job"
    threads = int(properties.get("threads") or 1)
    mem_mb = math.ceil(_required(resources, "mem_mb", rule))
    runtime_min = _required(resources, "runtime", rule)
    disk_mb = math.ceil(float(resources.get("disk_mb") or 0))
    gpus = int(resources.get("gpus") or 0)
    request = {
        "threads": threads,
        "mem_mb": mem_mb,
        "runtime_min": runtime_min,
        "disk_mb": disk_mb,
        "gpus": gpus,
    }

    requested = resources.get("queue")
    if requested:
        if requested not in table:
            raise SubmitError(
                f"rule {rule!r} asks for queue {requested!r}, which is not in the queue table; "
                "fix: add the row to queues.yaml or drop the `queue` resource"
            )
        if not table[requested]["enabled"]:
            raise SubmitError(
                f"rule {rule!r} asks for queue {requested!r}, which is disabled in the queue "
                "table; fix: enable the row in queues.yaml"
            )
        candidates = [(requested, table[requested])]
    else:
        candidates = [
            (name, row) for name, row in table.items() if row["enabled"] and row.get("auto", True)
        ]

    fits: list[Allocation] = []
    reasons: list[str] = []
    for name, row in candidates:
        reason = _misfit(row, **request)
        if reason:
            reasons.append(f"{name}: {reason}")
        else:
            fits.append(_allocation(name, row, **request))
    if not fits:
        raise SubmitError(
            f"no enabled queue fits rule {rule!r} (threads={threads}, mem_mb={mem_mb}, "
            f"runtime={runtime_min:g} min, disk_mb={disk_mb}, gpus={gpus}): "
            + "; ".join(reasons)
            + "; fix: change the request or enable a queue in queues.yaml"
        )
    return min(fits, key=lambda allocation: allocation.su_per_hour)


def pbs_log_path(properties: dict, subdir: str, stamp: str) -> Path:
    """Return the PBS log path: `<subdir>/<log stem>.<stamp>.log` beside the first declared log.

    A job without a declared log writes to `logs/<subdir>/<rule>.<jobid>.<stamp>.log`.
    """
    logs = properties.get("log") or []
    if logs:
        first = Path(logs[0])
        return first.parent / subdir / f"{first.stem}.{stamp}.log"
    rule = properties.get("rule") or properties.get("groupid") or "job"
    return Path("logs") / subdir / f"{rule}.{properties.get('jobid', 0)}.{stamp}.log"


def job_name(properties: dict) -> str:
    """Return a PBS job name from the rule: letters, digits, `_.-`, starting with a letter."""
    raw = str(properties.get("rule") or properties.get("groupid") or "job")
    name = re.sub(r"[^A-Za-z0-9_.-]", "_", raw)
    return name if name[:1].isalpha() else f"j{name}"


def build_command(
    args: argparse.Namespace, properties: dict, allocation: Allocation, log_path: Path
) -> list[str]:
    """Assemble the qsub argument list."""
    resources = (
        f"ncpus={allocation.ncpus},mem={allocation.mem_mb}MB,"
        f"walltime={allocation.walltime},jobfs={allocation.jobfs_mb}MB"
    )
    if allocation.ngpus:
        resources += f",ngpus={allocation.ngpus}"
    command = [
        *shlex.split(args.qsub),
        "-N",
        job_name(properties),
        "-q",
        allocation.queue,
        "-l",
        resources,
        "-l",
        "wd",
        "-j",
        "oe",
        "-o",
        str(log_path),
    ]
    if args.project:
        command += ["-P", args.project]
    if args.storage:
        command += ["-l", f"storage={args.storage}"]
    if args.pass_env:
        command += ["-v", ",".join(args.pass_env)]
    return [*command, str(args.jobscript)]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse the options the profile passes and the jobscript Snakemake appends."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "jobscript", type=Path, help="the jobscript Snakemake wrote (it appends this argument)"
    )
    parser.add_argument(
        "--queues",
        type=Path,
        default=Path(__file__).with_name("queues.yaml"),
        help="the queue table (default: queues.yaml beside this script)",
    )
    parser.add_argument(
        "--project", help="the PBS project to charge (-P); unset leaves it to PBS's default"
    )
    parser.add_argument("--storage", help="the -l storage list, for example gdata/a56+scratch/a56")
    parser.add_argument(
        "--pass-env",
        action="append",
        default=[],
        metavar="NAMES",
        help="comma-separated environment variables to copy into the job (repeatable)",
    )
    parser.add_argument(
        "--log-subdir",
        default="pbs",
        help="the directory beside the declared log for the PBS log (default: pbs)",
    )
    parser.add_argument(
        "--qsub", default="qsub", help="the qsub command (tests substitute a fake)"
    )
    args = parser.parse_args(argv)
    names: list[str] = []
    for group in args.pass_env:
        names += [name for name in group.split(",") if name]
    args.pass_env = names
    return args


def main(argv: list[str]) -> int:
    """Read the jobscript, choose the queue, submit, and print the PBS job id."""
    args = parse_args(argv)
    try:
        properties = read_job_properties(args.jobscript)
        allocation = allocate(properties, load_queue_table(args.queues))
    except SubmitError as error:
        print(f"submit_pbs: {error}", file=sys.stderr)
        return 2
    log_path = pbs_log_path(properties, args.log_subdir, time.strftime("%Y%m%dT%H%M%S")).absolute()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_command(args, properties, allocation, log_path)
    completed = subprocess.run(command, capture_output=True, text=True)
    rule = properties.get("rule") or properties.get("groupid") or "job"
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        print(
            f"submit_pbs: qsub refused {rule!r} (exit {completed.returncode}): {message}",
            file=sys.stderr,
        )
        print(f"submit_pbs: command was: {shlex.join(command)}", file=sys.stderr)
        return completed.returncode
    jobid = completed.stdout.strip()
    print(
        f"submit_pbs: {jobid} {rule} on {allocation.queue}: ncpus={allocation.ncpus} "
        f"mem={allocation.mem_mb}MB walltime={allocation.walltime} jobfs={allocation.jobfs_mb}MB"
        + (f" ngpus={allocation.ngpus}" if allocation.ngpus else "")
        + f", about {allocation.su_per_hour:.1f} SU/h; log {log_path}",
        file=sys.stderr,
    )
    print(jobid)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
