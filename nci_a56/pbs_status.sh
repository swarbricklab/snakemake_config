#! /bin/bash

# This script checks the status of a job that has been submitted to PBS Pro by Snakemake
# The script parses the results of 'qstat' and returns either 
#    - "running" (which includes "queued"
#    - "success" 
#    - "failed"

jobid=$1
log=logs/status_errors.log

status=$(qstat -x $jobid | grep $jobid | tr -s ' ' | cut -d ' ' -f5)
echo "$(date '+%Y-%m-%d %H:%M:%S') ::: $jobid ::: $status" >> $log
if [[ $status == "R" || $status == "Q" || $status == "E" ]]; then
    echo "running"
elif [[ $status == "F" ]]; then
    # check exit code
    exit_status=$(qstat -x $jobid -f -F dsv | sed 's/|/\n/g' | grep Exit_status)
    exit_status=${exit_status: -1}
    echo "$(date '+%Y-%m-%d %H:%M:%S') ::: $jobid ::: $exit_status" >> $log
    if [[ $exit_status == "0" ]]; then
        echo "success"
    else
        echo "failed"
    fi
elif [[ $status == "H" ]]; then
    echo "Job held. Check quota and resource requirements"
else
    # Unknown status, save log
    qstat -x $jobid | grep $jobid >> $log
    echo "failed"
fi