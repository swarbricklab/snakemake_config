# PBS Pro profile for NCI Gadi

This profile uses the `cluster-generic` executor with Snakemake 9.27.1.
It submits jobs with `qsub`, polls them with `qstat`
and cancels them with `qdel`. It requires the Gadi scheduler and shared storage.
Local adapter checks on Linux or macOS do not establish live PBS execution.

## Configure a deployment

Review `config.yaml` before using this profile:

| Setting | Required review |
|---|---|
| `PROJECT` environment variable | Set it to the allocation paying for the jobs. The profile reads it for `project` and derives `storage` as `gdata/` followed by that value. |
| `default-resources.storage` | Include every storage volume the jobs need. The derived default does not include other projects or scratch mounts. |
| `conda-prefix` | Replace the lab cache path with writable storage visible to compute jobs. |
| `apptainer-prefix`, `apptainer-args` | Review the lab image cache and bind paths for workflows using Snakemake's Apptainer integration. airrborne uses its own container wrapper and bind settings. |

Pass this directory to Snakemake's `--profile` option and supply the launching
workflow's `--workflow-profile`. Keep the workflow, inputs, outputs and caches
visible at the same paths on the launch and compute nodes. Follow the workflow's
preparation instructions before using compute nodes without network access.

The adapter chooses a queue from memory and jobfs requests unless the job
supplies `resources.queue`. Check the implementation against
[NCI's queue limits](https://opus.nci.org.au/display/Help/Queue+Limits) before
using another site or changing resource requests. Queue selection does not
validate every scheduler constraint.

## Files and behaviour

| File | Responsibility |
|---|---|
| `config.yaml` | Snakemake options, scheduler commands and default resources. |
| `key_mapping.yaml` | PBS submission options for the adapter's resource keys. |
| `pbs_submit.py` | Reads Snakemake job properties, selects the queue, converts walltime and submits the job. |
| `pbs_status.sh` | Returns `running`, `success` or `failed` for one job. |

`resources.threads` supplies PBS `ncpus`; native Snakemake `threads` supplies
workflow commands. Keep matching `set-threads` and `set-resources.threads`
entries for multithreaded rules. The
[shared-profile resource table](../README.md#resource-mapping) gives the units.

Each submission writes to a separate log under `logs/joblogs/<job-name>/`.
The job name is the rule name or group ID. The filename includes the Snakemake
job ID and a UUID, so retries retain earlier attempt logs.

The status script treats queued, running and held jobs as `running`. A finished
job succeeds only when its complete signed exit code is zero. Missing status or
an unrecognised state returns `failed`. Active states are cached for 120 seconds;
terminal states are queried again on each call. Completion is detected on the
first query after an active-state cache expires.

Each scheduler response is recorded in `logs/joblogs/job_status.log` with the
poll time, job ID, state and exit code. A held job also writes a diagnostic to
standard error when queried.

## Attribution

The submission adapter derives from work by Derrick Lin and
[metagenome-atlas/clusterprofile](https://github.com/metagenome-atlas/clusterprofile).
[THIRD_PARTY.md](../THIRD_PARTY.md) retains the source notices.

## Alternative adapters: `submit_pbs.py`, `status_pbs.py` and `queues.yaml`

The default profile selects `pbs_submit.py` and `pbs_status.sh`. The alternative
Python adapters below use `queues.yaml` and different resource, environment and
logging conventions. A workflow selects them explicitly and validates that
contract before switching. Both require Python 3 and PyYAML.

A workflow profile uses them like this (the scripts on `PATH`, or named by path):

```yaml
executor: cluster-generic
cluster-generic-submit-cmd: >-
  submit_pbs.py --project a56 --storage gdata/a56+scratch/a56 --umask 0027
cluster-generic-status-cmd: status_pbs.py --interval 60
cluster-generic-cancel-cmd: qdel
```

### `submit_pbs.py`

Reads the rule, `threads`, and the resources from the jobscript's `# properties = ` line
(`mem_mb`, `runtime` in minutes, `disk_mb`, and optionally `gpu`, Snakemake's standard GPU
count, and `queue`), chooses the cheapest enabled queue in `queues.yaml` that the job fits,
and submits it.

- The charge on Gadi is `SU per hour = rate x max(ncpus, memory share of a node)`, so the
  script prices every enabled row and takes the minimum. A large-memory job on few threads
  therefore goes to `hugemem` or `hugemembw`, whose nodes are bigger, rather than to
  `normal`. A rule can name a queue with a `queue` resource; that is the only way to reach
  a row marked `auto: false`, such as `copyq`.
- `ncpus` is `threads` raised to the queue's minimum (and whole GPUs on a GPU queue);
  memory is requested as declared; walltime comes from `runtime`; `jobfs` from `disk_mb`.
  A queue whose memory floor the request does not meet is not a candidate: the floors say
  which jobs belong on the large-memory nodes, and inflating a request to reach a cheaper
  rate would occupy those nodes and send most jobs to a small queue. Cores that the memory
  share already pays for are not requested either, because the charge is the same and a
  smaller request starts sooner.
- The PBS log (stdout and stderr joined) goes to a `pbs/` directory beside the job's first
  declared log, named after that log plus the submission time, so every attempt keeps its
  own file. A rule without a log writes to `logs/pbs/`.
- The environment is never exported wholesale (no `-V`). Snakemake's `envvars:` setting
  already exports each declared variable into the job command, so `--pass-env`, which
  copies further variables with `-v`, is rarely needed. `-l storage`, `-P`, and `-W umask`
  come from the profile's options; PBS's default umask of 077 makes the PBS log readable by
  its owner alone, and `--umask 0027` opens it to the group.
- One line per submission goes to stderr with the job id, queue, request, estimated SU per
  hour, and log path. A refused submission exits with `qsub`'s code and message.
- The PBS job name is the rule followed by its wildcard values, `rule.value.value`, so
  `qstat -u $USER` tells the sections of one rule apart (`qstat -w` shows the full name).

### `status_pbs.py`

Answers Snakemake with exactly one word, `running`, `success`, or `failed`, and never exits
non-zero, because anything else aborts the whole workflow.

- Snakemake calls it once per active job per polling round. The script keeps a small cache
  under `.snakemake/pbs_status/` in the working directory and asks `qstat -x -f -F json`
  about all the jobs it is watching in one call, at most once per `--interval` seconds
  (default 60). Hundreds of active jobs therefore cost one `qstat` a minute.
- Queued, running, held, suspended, and exiting jobs are `running`; a held job is logged
  once. A finished job is `success` on `Exit_status` 0 and `failed` otherwise; negative
  statuses are PBS kills (`-29` is the walltime limit). A job `qstat` no longer knows,
  which happens 24 hours after it finished, is `failed`, so Snakemake redoes it rather than
  waiting forever. A `qstat` that fails or times out changes nothing and answers `running`.
- Events go to `.snakemake/pbs_status/status.log`.

### `queues.yaml`

The Gadi queue table: rates, node sizes, per-job limits, and the floors the scheduler
enforces, with the date they were checked. A row is enabled once a job of the project has
run on that queue; `gpuvolta` is present and disabled until a workflow needs it.

The scripts are tested from the seamark repository, which checks this repository out as a
submodule, against a fake `qsub` and `qstat` (`tests/unit/profiles/test_gadi_pbs_scripts.py`
there).
