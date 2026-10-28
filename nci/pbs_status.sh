#!/bin/bash

# Report the PBS state using Snakemake's running, success and failed values.
set -u
jobid=$1
log=logs/joblogs/job_status.log
mkdir -p "$(dirname "$log")"

# Cache only active states. Terminal states must retain their final result.
last=$(awk -F '\t' -v id="$jobid" '$2 == id {row=$0} END {print row}' "$log" 2>/dev/null || true)
if [[ -n "$last" ]]; then
    IFS=$'\t' read -r last_time _ last_status _ <<< "$last"
    if [[ "$last_status" =~ ^(R|Q|E|H|W|T|S)$ ]] && (( $(date +%s) - last_time <= 120 )); then
        echo running
        exit 0
    fi
fi

if ! details=$(qstat -x "$jobid" -f -F dsv); then
    echo "PBS status is unavailable for job $jobid." >&2
    echo failed
    exit 0
fi
status=$(printf '%s\n' "$details" | tr '|' '\n' | sed -n 's/^[[:space:]]*job_state[[:space:]]*=[[:space:]]*\([^[:space:]]*\)[[:space:]]*$/\1/p')
exit_status=$(printf '%s\n' "$details" | tr '|' '\n' | sed -n 's/^[[:space:]]*Exit_status[[:space:]]*=[[:space:]]*\(-\{0,1\}[0-9][0-9]*\)[[:space:]]*$/\1/p')
printf '%s\t%s\t%s\t%s\n' "$(date +%s)" "$jobid" "$status" "$exit_status" >> "$log"
case "$status" in
    R|Q|E|H|W|T|S)
        if [[ "$status" == H ]]; then
            echo "PBS job $jobid is held. Check quota and resource requirements." >&2
        fi
        echo running
        ;;
    F)
        if [[ "$exit_status" == 0 ]]; then
            echo success
        else
            echo failed
        fi
        ;;
    *)
        echo "PBS returned an unrecognised state for job $jobid: $status." >&2
        echo failed
        ;;
esac
