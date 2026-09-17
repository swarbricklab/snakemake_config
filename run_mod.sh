#! /bin/bash

set -e
workflow=$1; shift
eval  "$(conda shell.bash hook)"
conda activate snakemake_7.32.4

if [[ "$(hostname)" == *"nci"* ]]; then
    echo "Running on NCI"
    global_profile="--profile modules/$workflow/profiles/global/nci"
    workflow_profile="--workflow-profile modules/$workflow/profiles/workflow "
    module load singularity
    mkdir -p logs/joblogs
else
    echo "WARNING: Unknown host: $(hostname)"
    echo "WARNING: No known global profile for this host"
    echo "WARNING: Running without global profile"
    echo "See https://github.com/swarbricklab/snakemake_config/blob/main/README.md"
    global_profile=""
fi

snakemake $global_profile $workflow_profile \
    --snakefile modules/$workflow/workflow/Snakefile \
    --configfile config/$workflow/soup-or-cell/config.yaml \
    $@
