# Resources

This directory holds a PBS job template for 10x Genomics tools and a separate
`qsub` wrapper. airrborne uses neither file to submit its analysis jobs; its
site profile selects the adapters described in the [NCI guide](../README.md).

## Contents

This directory contains the following resources:
- `pbspro.template`
- `qsub`

### `pbspro.template`

This jobscript template is used by 10X software such as `cellranger` and `spaceranger` when in "cluster mode".
The template has been adapted from the [10X website](https://www.10xgenomics.com/support/software/cell-ranger/latest/advanced/cr-job-submission-mode#torque-pbs-fa77ac) adding extra directives for project and storage.
The template can be adapted for use with other projects, etc.

Note that this is a jobscript _template_, not an actual jobscript.
10X tools such as `cellranger` will create jobscripts based on this template by populating the variables.

Martian fills the CPU and memory placeholders from its stage resource
requests. Those requests do not guarantee that a particular dataset will fit.
Review scheduler accounting and the tool's resource-override options after a
pilot. The template also hard-codes project `a56`, queue `normal`, an 8-hour
walltime and three storage volumes. Review those directives for the deployment.

> **This template is not what the profile currently uses, but do not remove it.**
>
> There are two ways to run 10X tools against PBS Pro:
>
> 1. `--jobmode=<path to this template>`, for a tool version supporting a custom
>    submission template; or
> 2. `--jobmode=pbspro`, when the installed tool includes a job manager with
>    that name.
>
> `config.yaml` supplies `jobmode: "pbspro"` to workflows that read that
> resource. A configuration value alone does not establish that the installed
> tool supports it. The proposed PBS Pro job manager is described in
> [martian-lang/martian#151](https://github.com/martian-lang/martian/pull/151).
> Check the installed tool's job managers and help rather than inferring
> support from the pull request.
>
> For a version supporting custom templates, point `jobmode` at this file and
> validate a small submission after reviewing its site-specific directives:
>
> ```yaml
> default-resources:
>   jobmode: "'profiles/global/nci/resources/pbspro.template'"
> ```
>
> Note the nested quotes, which are needed because the value is a path passed through to the 10X command line.

### `qsub`

This wrapper accepts one jobscript path or reads a script from standard input.
It extracts the integer after `#PBS -l mem=`. When that number exceeds 192,
it replaces the queue with `hugemem` and adds `jobfs=400GB`, then submits
through `/opt/pbs/default/bin/qsub`.

The parser does not convert memory units or validate queue, CPU, walltime or
storage limits. Its comparison assumes the memory number is in gigabytes, so
an MB request does not have the same meaning. This wrapper does not establish
that a job fits a queue. It also edits a supplied jobscript in place.
