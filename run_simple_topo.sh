#!/bin/bash
#
# Reproduce basic TCP Outcast result on Mininet using a simplified topology.

# Bandwidth in Mbps.
BW=100;
# Queue size in KB.
Q="128kb";
# Hz value estimate.
HZ=5000;
# Path to iperf binary to use.
IPERF="/usr/bin/iperf";
# Number of seconds to run each experiment for.
T=10;
# Number of ms to set rtoMin to.
RTO_MIN="2ms";


# Disable all fancy TCP settings on the VM, otherwise Outcasting is the least of
# our problems.
sysctl -w net.ipv4.tcp_dctcp_enable=0
sysctl -w net.ipv4.tcp_ecn=0
sysctl -w net.mptcp.mptcp_enabled=0


safe_mkdir() {
    dir=$1
    echo $dir
    test -d $dir
    if [ "$?" -eq "0" ]; then
	rm -rf $dir
    fi
    mkdir $dir
}

results_dir="results_simple"
safe_mkdir $results_dir

# Run one experiment with the specified n1, n2 paramters.
run_once() {
    n1=$1
    n2=$2
    d=$3
    python tcp_outcast.py --n1 $n1 --n2 $n2 --bw $BW -t $T \
        -d $d --rto_min=$RTO_MIN --queue_size=$Q --iperf=$IPERF --hz=$HZ \
        --impatient=true --use_tbf=true
    python join_tcpdump.py -f s0-eth1=$d/tcp_dump.s0-eth1.txt  \
        -f s0-eth3=$d/tcp_dump.s0-eth3.txt -f s0-eth2=$d/tcp_dump.s0-eth2.txt \
        -s s0-eth1=10.0.0.1 -s s0-eth2=10.0.0.2 -s s0-eth3=10.0.0.3 \
        > $d/tcpdump_join.txt

}

d1="$results_dir/n1-1-n2-2"
d2="$results_dir/n1-1-n2-6"
d3="$results_dir/n1-1-n2-12"

run_once 1 2 $d1
run_once 1 6 $d2
run_once 1 12 $d3

# Plot the main result.
python generate_plots.py \
    --tcpdump=$d1/tcp_dump.s0-eth1.txt \
    --tcpdump=$d2/tcp_dump.s0-eth1.txt \
    --tcpdump=$d3/tcp_dump.s0-eth1.txt \
    -r "10.0.0.1:5001" \
    -o $results_dir/result \
    --bucket_size_ms=100 \
    --end_time_ms=10000 \
    --start_time_ms=0
# Plot drops for the n1=1 n2=12 case.
python generate_plots.py \
    --tcpdump_join=$d3/tcpdump_join.txt \
    -r "10.0.0.1:5001" \
    -o $results_dir/result \
    --bucket_size_ms=100 \
    --end_time_ms=10000 \
    --start_time_ms=0
