# Third-party material

Two files in this repository are derived from third-party work. Both are under
permissive licences compatible with this repository's MIT licence, but each
requires that the original notice be retained. Those notices are reproduced
below and in the files themselves.

## `nci/pbs_submit.py`

Derived from `scheduler.py` in [metagenome-atlas/clusterprofile](https://github.com/metagenome-atlas/clusterprofile),
by way of a simplified version authored by Derrick Lin.

The `key_mapping.yaml` approach used by this profile -- mapping human-readable
resource names onto scheduler-specific submission options, keyed on a `system`
value -- comes from the same source, as does `nci/key_mapping.yaml`.

Our version keeps the overall structure and much of the code, and adds
NCI-specific queue selection (`select_queue`) and walltime handling
(`calculate_walltime`).

> MIT License
>
> Copyright (c) 2017 Silas Kieser

## `nci/resources/pbspro.template`

Adapted from the PBS Pro jobscript template published by 10x Genomics, which
ships with the [martian](https://github.com/martian-lang/martian) runtime as
`jobmanagers/pbspro.template.example` (martian itself is MIT licensed). Our
version adds `-P` (project) and `-l storage=` directives for NCI.

The original 10x copyright notice is retained in the file.

> Copyright (c) 2016 10x Genomics, Inc. All rights reserved.
