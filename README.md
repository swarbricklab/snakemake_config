# Global Snakemake Profiles

This repo tracks global Snakemake profiles used by the Swarbrick Lab on the following platforms:
- The Australian National Compute Infrastructure (NCI)
- The Garvan HPC

Profiles for additional platforms will be added as the need arises.
The options specified here can also be used as a starting point for extending to other platforms.

## Profiles

Snakemake supports a large number of [command line options](https://snakemake.readthedocs.io/en/v7.32.3/executing/cli.html) for fine-tuning behaviour.
These options can also be specified by way of YAML [profile files](https://snakemake.readthedocs.io/en/v7.32.3/executing/cli.html#profiles), where each key in the profile corresponds to a command line option.

From v7.29.0, Snakemake supports kinds of profiles:
1. global profiles (specified via `--profile`)
2. workflow-specific profiles (specifed via `--workflow-profile`)

Value options from all sourced are merged, with the following priority:
```
command line > workflow profile > global profile > rule specifications > default value
```
That is, values specified from the command line override specifications in the workflow profile, and so on.

## Global versus workflow profiles

Submitting a job to a job scheduler such as PBS or SGE typically involves specifying account-specific or platform-specific information, such as account (project), queues or partitions (storage volumes).
Such values are not intrinsic to the workflow.
That is, the workflow could be run on single server (assuming sufficient compute resources) without submitting any jobs at all, or the same workflow could be run by a different team using different account (project) credentials and a different storage volume.
Moreover, the same project, queue and storage values can be used across multiple workflows.

Options such as the above are good candidates for **global profiles**. 
The values in these global profiles can be loaded by multiple workflows.

Other values are required in order for a workflow to run.
For example, if a workflow uses `conda` to define the environments for certain rules, then conda needs to be enabled in order for the workflow to run as intended.
Similarly, if it is known that certain rules fail when there is not enough memory, and that it is sometimes necessary to retry several times, allocating extra memory each time, then options associated with retrying failed jobs may be necessary in order for the workflow to run successfully.

Options such as the above are good candidates for **workflow profiles**.
These options need to be included in the workflow repo in order for the workflow to run reliably.

## Grey options

There is a grey area involving options that are useful but not required.
These could be specified in either the global profile or the workflow, or even from the command line.
In that sense, it does not really matter where the options are specified.

> However, from a reproducibility perspective it is critical to track which options were actually used at the time when a workflow was applied to a particular dataset.
> See below for notes on how to achieve this.

From a practical standpoint, common options that we typically use across workflows will be included in the global profiles.
These values can be overridden by workflow profiles if necessary, or even from the command line.
However command line specifications are difficult to track with version control, unless they are embedded in a script that is tracked (such as "run" scripts or `dvc.yaml`).
So although it is acceptable to override profile options from the command line for testing purposes (or even specify additional options not included in any profiles), once a decision is made on the desired values should be embedded in either a profile or a script.

## Activation

Specify the **global** profile with the `--profile` option and the **workflow** profile with the `--workflow-profile` option.
Both options can be specified together

### Paths

Both global profiles and workflow profiles are activated by specifying the path to the _directory_ containing a `config.yaml` file that specifies the options for the profile.
Do not specify the path to the `config.yaml` file itself.

> Both absolute and relative paths are supported, but relative paths are preferred.

For workflow profiles, paths should be relative to the directory where the `snakemake` command is executed.
In stand-alone mode, this equates to the top level of the workflow repo.
In module mode, this translates to the top level of the dataset repo.

For global profiles, Snakemake will also search paths relative to `$XDG_CONFIG_DIRS/snakemake`.
On NCI, the `XDG_CONFIG_DIRS` environment variable is set to `/g/data/a56/config` when the `snakemake_7.32.4` conda environment is activated, but you can set this variable to alternative location in order to test alternative profiles.

However, the preferred solution is to embed global profiles into workflow repos by installing this repo as a submodule of the workflow repo.
This allows _a particular version_ of the global profile to be specified via a relative path from the top level of the workflow or dataset repo.
A side benefit of this approach is the inclusion of this documentation in the workflows and datasets that use these profiles.

TODO: Add example

## Version control

> The advice below is aspirational, and may change as we try this out in actual practice.

From a reproducibility standpoint, it is important that we track which version of each profile was used when running workflows on datasets, or when testing worfklows against test data.

Workflow profiles are specified as part of the repo for the workflow, ideally under `workflow/profile`, and can be tracked by git directly.
Changes to the workflow profile should be tracked by git, either by updating the `main` branch of the repo with the new changes, or by creating a branch to track the changes -- regardless of whether there is any intention to merge this branch into `main`.
We need to track what we actually do, even if it is a one-off change.

Global profiles are tracked via this repo.
However, when a profile in this repo is used (either to test a workflow or to process a dataset) we need to track the particular version that is used.
This can be achieved by embedding this repo into the workflow repo as a git submodule.
The submodule can then be checked out to the specific revision (version/branch) required, and this version can be tracked in the parent repo (workflow or dataset).

## Resources

As well as command line options, profiles can also include resource specifications.
Any default resources specified in the global profile will provide default values for rules that do not specify resource requirements.
These default resources include account credentials, such as `project: a56`, which can be inherited by every workflow using the global profile.

> Important note: default resources specified in workflow profiles completely mask those specified in global profiles.
> Unlike other options, the default resources in one profile are NOT interleaved with the other.
> Accordingly, `default-resources` should NOT be specified in workflow profiles.
> If you need to specify the resource requirements for a rule, this can be done either within the rule definition or via `set-resources` in the workflow profile.
> The latter over-rides the former.

### Standard resources

Both global and workflow profiles should, where possible, use the "standard resources" recognized by Snakemake, including:
- `mem`     = total memory (not memory per CPU). Requires suffix such as "MB" or "GB"
- `disk`    = total local disk space (not per CPU). Requires suffix
- `threads` = equivalent to "cores" as not all CPU cores are multi-threaded
- `runtime` = translates to "walltime" on HPC systems

TODO: Add notes on runtime

Internally, Snakemake translates `mem` and `disk` into `mem_mb`, `mem_gb`, `disk_mb`, `disk_gb`, etc.
These resource items are equivalent to `mem` and `disk` except that they are integars, with the units implied by the resource name.
Rules and scripts can utilize whichever form is most convenient, but the recommendation is to specify the resource requirements via `mem` and `disk` and let Snakemake do the conversions.

### Non-standard resources

Other than the recommended standard resources above, resource keys are free form.
However, we have defined the following additional resources to support execution in a cluster environment:
- `project` : Used for HPC acount purposes, eg "a56" or "TumourProgression"
- `storage` : which storage volume to mount, eg "gdata/a56" or "/directflow"
- `queue`   : which queue to submit jobs to, eg "normal", "copyq"

Use these resources in additional to standard resources when appropriate.
The values specified via these resources can be translated into platform-specific job submission options via key mappings.
This simplifies portability between HPCs, and between HPCs and other execution platforms.

Additional resources can be defined if necessary.
In this event, consider whether the new resources should be incorporated into the list above and documented here.
