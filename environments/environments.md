# Snakemake environments

This directory tracks conda [environment definition files](https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html#creating-an-environment-from-an-environment-yml-file) used to create conda environments for running Snakemake workflows.

Members of the Swarbrick Lab can access pre-built environments via standardised `~/.condarc` settings.
Consult the wiki for details.

If the required environment is not available, it can be created from the environment definition file as follows:
```
conda env create -f {EDF}
```
Here `{EDF}` is the environment definition file.

For example ..
```
conda env create -f snakemake_7.32.4.yaml
```

The location of the conda environment created by this command is determined by your `~/.condarc` and defaults to `~/.conda` if you do not have a `~/.condarc` file.
