#! /bin/bash

# This script checks the status of a job that has been submitted to PBS Pro by Snakemake
# The script parses the results of 'qstat' and returns either 
#    - "running" (which includes "queued"
#    - "success" 
#    - "failed"

jobid=$1
log=logs/status_errors.log

# Make sure error log exists
if [ ! -f $log ]; then
    touch $log
fi

# Check time of last poll and exit with "running" if less than two minutes have elapsed
if grep -q $jobid $log; then
    last_time=$(grep -q $jobid $log | cut -d ' ' -f 1)
    current_time=$(date +%s)
    time_diff=$(( current_time - last_time ))
    if [ $time_diff -le 120 ]; then
        echo "running"
        exit
    fi
fi

status=$(qstat -x $jobid | grep $jobid | tr -s ' ' | cut -d ' ' -f5)
echo "$(date '+%s') $jobid $status" >> $log
if [[ $status == "R" || $status == "Q" || $status == "E" ]]; then
    echo "running"
elif [[ $status == "F" ]]; then
    # check exit code
    exit_status=$(qstat -x $jobid -f -F dsv | sed 's/|/\n/g' | grep Exit_status)
    exit_status=${exit_status: -1}
    echo "$(date '+%s') $jobid $exit_status" >> $log
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
