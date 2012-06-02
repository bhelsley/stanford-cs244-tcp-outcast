#!/bin/sh

safe_mkdir() {
    dir=$1
    echo $dir
    test -d $dir
    if [ "$?" -eq "0" ]; then
	rm -rf $dir
    fi
    mkdir $dir
}

results_dir="results"
safe_mkdir $results_dir

run_single_experiment() {
    n1=$1
    n2=$2
    subdir="$results_dir/fattree_${n1}_${n2}"
    safe_mkdir $subdir

    echo -e "Running experiment with $n1 2-hop flows and $n2 6-hop flows.\n"
    for i in `seq 1 10`; do 
	dir="$subdir/$i"
	mn -c
	python tcp_outcast.py --n1 $n1 --n2 $n2 --bw 100 -d $dir -t 10 \
	    --ft=True --impatient=True
	python generate_plots.py --tcpdump=$dir/tcp_dump.0_0_1-eth2.txt \
	    -r "10.0.0.2:5001" --outcast_host "10.0.0.3" -o $dir/result_500 \
	    --bucket_size_ms=20 --end_time_ms=500
	python generate_plots.py --tcpdump=$dir/tcp_dump.0_0_1-eth2.txt \
	    -r "10.0.0.2:5001" --outcast_host "10.0.0.3" -o $dir/result_5000 \
	    --bucket_size_ms=20 --end_time_ms=5000
    done
}

run_single_experiment 1 2
run_single_experiment 1 6
run_single_experiment 1 12
run_single_experiment 10 120
run_single_experiment 20 240
run_single_experiment 30 360
