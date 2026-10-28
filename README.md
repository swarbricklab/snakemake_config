# Shared Snakemake profiles

This repository supplies a PBS Pro profile for NCI Gadi, used by Swarbrick Lab
workflows with Snakemake 9.27.1. It contains no Garvan profile. The NCI profile
requires Gadi commands and storage; it is not a local Linux or macOS profile.
Use the launching workflow's instructions for local execution and environments.

## Add the profile to a workflow

From the workflow repository root:

```bash
mkdir -p profiles
git submodule add https://github.com/swarbricklab/snakemake_config.git profiles/global
```

For an existing checkout that already declares this submodule:

```bash
git submodule update --init --recursive
```

Commit the submodule revision with the workflow. Keep workflow-specific settings
in `profiles/workflow/config.yaml` and record the launch command with each run.
A relative profile path resolves from the launch directory. Pass the directory
containing `config.yaml`, not the file itself.

## Choose where settings belong

Snakemake reads global settings through `--profile` and workflow settings through
`--workflow-profile`. Command-line options override workflow-profile options,
which override global-profile options. See the
[Snakemake profile reference](https://snakemake.readthedocs.io/en/v9.27.1/executing/cli.html#profiles).

| Location | Settings |
|---|---|
| Global profile | Scheduler commands, project, storage, shared caches and submission limits. |
| Workflow profile | Required execution features and per-rule CPU, memory and time requests. |
| Launch command | Run-specific choices, recorded with the run. |

`default-resources` is replaced as a whole when a later profile supplies it.
Keep shared defaults in the global profile and use `set-resources` for individual
rules in the workflow profile. Otherwise a workflow can lose its project and
storage defaults.

## Resource mapping

The [NCI guide](nci/README.md) describes deployment. Its adapter reads these
resource keys from Snakemake job properties:

| Key | Meaning in this adapter |
|---|---|
| `threads` | CPU allocation passed to PBS `ncpus`. This resource is separate from Snakemake's native rule `threads`. Keep both values equal. |
| `mem_mb` | Total job memory in MB, passed to PBS `mem`. |
| `disk_mb` | Job-local disk space in MB, passed to PBS `jobfs`. |
| `runtime` | Minutes, converted to PBS walltime in seconds. |
| `project` | Allocation charged for the job. |
| `storage` | Gadi storage mounts passed to PBS. |
| `queue` | Optional explicit queue; otherwise the adapter chooses from memory and jobfs requests. |

Requested resources are not measurements of tool requirements. Validate them
against scheduler accounting. The adapter contains Gadi-specific queue logic
in Python as well as `nci/key_mapping.yaml`; changing the mapping alone does not
port it to another scheduler.

## Other files

- [environments/environments.md](environments/environments.md) describes the
  separate lab utility environment.
- [nci/resources/resources.md](nci/resources/resources.md) describes the 10x
  template and the separate `qsub` wrapper.
- `run_mod.sh` is a launcher for a specific parent layout under `modules/` and
  `config/`. Its hard-coded `soup-or-cell` configuration path does not launch
  airrborne. Use the workflow's own launcher.

## Licence

See the [MIT licence](LICENSE) and the retained notices in
[THIRD_PARTY.md](THIRD_PARTY.md).
