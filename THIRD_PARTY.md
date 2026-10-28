# Third-party material

This repository includes material from two third-party sources. Their notices
are retained below and beside the derived code. The sources use permissive
licences compatible with this repository's MIT licence.

## `nci/pbs_submit.py`

Derived from `scheduler.py` in [metagenome-atlas/clusterprofile](https://github.com/metagenome-atlas/clusterprofile),
by way of a simplified version authored by Derrick Lin.

The `key_mapping.yaml` approach used by this profile maps resource names to
scheduler-specific submission options, keyed on a `system` value. It comes
from the same source, as does `nci/key_mapping.yaml`.

The adapter keeps the structure and much of the code, and adds
NCI-specific queue selection (`select_queue`) and walltime handling
(`calculate_walltime`).

> MIT License
>
> Copyright (c) 2017 Silas Kieser

## `nci/resources/pbspro.template`

Adapted from the PBS Pro jobscript template published by 10x Genomics, which
ships with the [martian](https://github.com/martian-lang/martian) runtime as
`jobmanagers/pbspro.template.example` (martian itself is MIT licensed). This
version adds `-P` (project) and `-l storage=` directives for NCI.

The original 10x copyright notice is retained in the file.

> Copyright (c) 2016 10x Genomics, Inc. All rights reserved.
