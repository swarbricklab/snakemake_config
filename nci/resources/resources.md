# Resources

This directory contains resources that may be used by multiple Snakemake workflows.
Placing these resources here avoids duplication and allows all workflows that utilise these resources to take advantage of any improvements.

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

In particular, `cellranger` etc will determine how many resources to request (memory, CPUs, etc) based on benchmarking data accumulated by 10X.
Generally, these resource estimates are quite accurate, resulting in very efficient resource allocation.
Occasionally, however, `cellranger` etc will underestimate the amount of memory required, for example.
In such cases, it is possible to override the default resource allocations.

> **This template is not what the profile currently uses, but do not remove it.**
>
> There are two ways to run 10X tools against PBS Pro:
>
> 1. `--jobmode=<path to this template>`, which works with **any** build of `cellranger`; or
> 2. `--jobmode=pbspro`, which uses a job manager built into the Martian runtime that 10X tools are built on.
>
> `config.yaml` sets `jobmode: "pbspro"`, so option 2 is the active path. However, the `pbspro` job manager is **not** in the upstream Martian runtime -- upstream ships only a `pbspro.template.example`, with no registered job manager. It was contributed in [martian-lang/martian#151](https://github.com/martian-lang/martian/pull/151), which at the time of writing is approved but not yet merged. Until a Martian release includes it, option 2 requires a `cellranger` built against a patched Martian.
>
> This template is therefore the fallback that works with a stock `cellranger`, and is what anyone outside the lab should use to reproduce our 10X processing. Point `jobmode` at this file instead:
>
> ```yaml
> default-resources:
>   jobmode: "'profiles/global/nci/resources/pbspro.template'"
> ```
>
> Note the nested quotes, which are needed because the value is a path passed through to the 10X command line.

### `qsub`

This wrapper script intercepts `qsub` calls and rewrites the jobscript to ensure that the queue requested can cater for the resources requested.
The wrapper then passes the edited jobscript on to the system `qsub`.
