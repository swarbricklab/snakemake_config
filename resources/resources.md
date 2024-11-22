# Resources

This directory contains resources that may be used by multiple Snakemake workflows.
Placing these resources here avoids duplication and allows all workflows that utilise these resources to take advantage of any improvements.

## Contents

This directory contains the following resources:
- `pbspro.template`

### `pbspro.tempate`

This jobscript template is used by 10X software such as `cellranger` and `spaceranger` when in "cluster mode".
The template has been adapted from the [10X website](https://www.10xgenomics.com/support/software/cell-ranger/latest/advanced/cr-job-submission-mode#torque-pbs-fa77ac) adding extra directives for project and storage.
The tempate can be adapted for use with other projects, etc.

Note that this is a jobscript _template_, not an actual jobscript.
10X tools such as `cellranger` will create jobscripts based on this template by populating the variables.

In particular, `cellranger` etc will determine how many resources to request (memory, CPUs, etc) based on benchmarking data accumuated by 10X.
Generally, these resource estimates are quite accurate, resulting in very efficient resource allocation.
Occassionally, however, `cellranger` etc will underestimate the amount of memory required, for example.
In such cases, it is possible to override the default resource allocations.
