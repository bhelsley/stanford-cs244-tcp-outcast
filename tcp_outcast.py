#!/usr/bin/python

"CS244 Assignment 1: Parking Lot"

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.log import lg, output
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import irange, custom, quietRun, dumpNetConnections
from mininet.cli import CLI

from time import sleep, time
from multiprocessing import Process
from subprocess import Popen
import termcolor as T
import argparse

import sys
import os
from util.monitor import monitor_devs_ng

def cprint(s, color, cr=True):
    """Print in color
       s: string to print
       color: color to use"""
    if cr:
        print T.colored(s, color)
    else:
        print T.colored(s, color),

parser = argparse.ArgumentParser(description="Parking lot tests")

parser.add_argument('--dir', '-d',
                    help="Directory to store outputs",
                    default="results")

parser.add_argument('--n1',
                    type=int,
                    help=("Number of h1 flows.  Must be >= 1"),
                    required=True)

parser.add_argument('--n2',
                    type=int,
                    help=("Number of h2 flows.  Must be >= 1"),
                    required=True)

parser.add_argument('--time', '-t',
                    dest="time",
                    type=int,
                    help="Duration of the experiment.",
                    default=60)
                    
parser.add_argument('--bw', '-b',
                    type=float,
                    help="Bandwidth of network links (in Mbps)",
                    default=10)

# Expt parameters
args = parser.parse_args()

if not os.path.exists(args.dir):
    os.makedirs(args.dir)

lg.setLogLevel('info')

class SingleSwitchOutcastTopo(Topo):
  "Simple topology with one switch and three hosts to reproduce behavior."""

  def __init__(self, cpu=0.3, bw=10, *args, **kwargs):
    Topo.__init__(self, *args, **kwargs)

    hconfig = {}
    lconfig = {}

    h0 = self.add_host('h0')
    h1 = self.add_host('h1')
    h2 = self.add_host('h2')

    s0 = self.add_switch('s0')

    self.add_link(h0, s0, port1=0, port2=0, **lconfig)
    self.add_link(h1, s0, port1=0, port2=1, **lconfig)
    self.add_link(h2, s0, port1=0, port2=2, **lconfig)


def waitListening(client, server, port):
    "Wait until server is listening on port"
    if not 'telnet' in client.cmd('which telnet'):
        raise Exception('Could not find telnet')
    cmd = ('sh -c "echo A | telnet -e A %s %s"' %
           (server.IP(), port))
    while 'Connected' not in client.cmd(cmd):
        output('waiting for', server,
               'to listen on port', port, '\n')
        sleep(.5)

def start_tcpprobe():
    os.system("rmmod tcp_probe &>/dev/null; modprobe tcp_probe;")
    Popen("cat /proc/net/tcpprobe > %s/tcp_probe.txt" % args.dir, shell=True)

def stop_tcpprobe():
    os.system("killall -9 cat; rmmod tcp_probe &>/dev/null;")

def run_outcast(net, n_h1, n_h2):
    "Run experiment"

    seconds = args.time

    # Start the bandwidth and cwnd monitors in the background
    monitor = Process(target=monitor_devs_ng,
            args=('%s/bwm.txt' % args.dir, 1.0))
    monitor.start()
    start_tcpprobe()

    # Get receiver and clients
    recvr = net.getNodeByName('h0')
    h1 = net.getNodeByName('h1')
    h2 = net.getNodeByName('h2')

    # Start the receiver
    port = 5001
    recvr.cmd('iperf -s -p', port,
              '> %s/iperf_server.txt' % args.dir, '&')

    waitListening(h1, recvr, port)

    for i in xrange(n_h1):
        h1.cmd('iperf -Z reno -c %s -p %s -t %d -i 1 -yc > %s/iperf_%s.%d.txt &' % (
            recvr.IP(), 5001, seconds, args.dir, 'h1', i))
    for i in xrange(n_h2):
        h2.cmd('iperf -Z reno -c %s -p %s -t %d -i 1 -yc > %s/iperf_%s.%d.txt &' % (
            recvr.IP(), 5001, seconds, args.dir, 'h2', i))

    # TODO(bhelsley): intelligent wait to detect when client iperf processes
    # have exited.
    sleep(seconds + 5)

    recvr.cmd('kill %iperf')

    # Shut down monitors
    monitor.terminate()
    stop_tcpprobe()

def check_prereqs():
    "Check for necessary programs"
    prereqs = ['telnet', 'bwm-ng', 'iperf', 'ping']
    for p in prereqs:
        if not quietRun('which ' + p):
            raise Exception((
                'Could not find %s - make sure that it is '
                'installed and in your $PATH') % p)

def main():
    "Create and run experiment"
    start = time()

    topo = SingleSwitchOutcastTopo() 

    host = custom(CPULimitedHost, cpu=.15)  # 15% of system bandwidth
    link = custom(TCLink, bw=args.bw, delay='1ms',
                  max_queue_size=200)

    net = Mininet(topo=topo, host=host, link=link)

    net.start()

    cprint("*** Dumping network connections:", "green")
    dumpNetConnections(net)

    cprint("*** Testing connectivity", "blue")

    net.pingAll()

    cprint("*** Running experiment", "magenta")
    run_outcast(net, n_h1=args.n1, n_h2=args.n2)

    net.stop()
    end = time()
    os.system("killall -9 bwm-ng")
    cprint("Experiment took %.3f seconds" % (end - start), "yellow")

if __name__ == '__main__':
    check_prereqs()
    main()

