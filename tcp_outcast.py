#!/usr/bin/python

"CS244 Assignment 1: Parking Lot"

import re

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.log import lg, output
from mininet.node import CPULimitedHost, RemoteController
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

parser.add_argument('--rto_min',
                    help=('minRTO value to set on hosts.'),
                    default='2ms')

parser.add_argument('--queue_size',
                    help=('queue size to set on switch.'),
                    default='16KB')

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
    lconfig = {'bw' : bw}

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
    os.system("rmmod tcp_probe 1> /dev/null 2>&1; modprobe tcp_probe;")
    Popen("cat /proc/net/tcpprobe > %s/tcp_probe.txt" % args.dir, shell=True)

def stop_tcpprobe():
    os.system("killall -9 cat; rmmod tcp_probe &>/dev/null;")

def run_outcast(net, receiver, hosts_2hop, hosts_6hop, n_2hops, n_6hops,
                rto_min, queue_size):
    """Run outcast experiment.

    Args:
      receiver: the receiver node.
      hosts_2hop: a list of host node objects for host nodes
                  at 2 hops from receiver sending data to receiver.
      hosts_6hop: a list of host node objects for host nodes
                  at 6 hops from receiver sending data to receiver.
      n_2hops: number of flows per 2-hop host.
      n_6hops: number of flows per 6-hop host.
      rto_min: RTO min time setting for each host as string.
      queue_size: Queue size of each switch.
    """

    seconds = args.time

    # Start the bandwidth and cwnd monitors in the background
    monitor = Process(target=monitor_devs_ng,
                      args=('%s/bwm.txt' % args.dir, 1.0))
    monitor.start()
    start_tcpprobe()

    print 'Setting minRTO on each host...'
    # TODO(bhelsley): I think this can be done with os.system anyway.
    cmd = 'ip route replace dev %%s-eth0 rto_min %s' % rto_min
    # for receiver.
    print '  %s  %s' % (str(receiver), receiver.cmd(cmd % str(receiver)))
    # for each 2 hop host.
    for host in hosts_2hop:
        print '  %s  %s' % (str(host), host.cmd(cmd % str(host)))
    # for each 6 hop host.
    for host in hosts_6hop:
        print '  %s  %s' % (str(host), host.cmd(cmd % str(host)))

    # TODO(harshit): Set it for all switches agnostic of topography.
    print 'Setting queue size to %s for all switches...' % queue_size
    cmd = ("tc qdisc change dev %s parent 1:1 "
           "handle 10: netem limit %s" % ('s0-eth0', queue_size))
    os.system(cmd)

    print 'Starting flows...'

    # Start the receiver
    port = 5001
    receiver.cmd('iperf -s -p', port,
                 '> %s/iperf_server.txt' % args.dir, '&')

    # Wait till the receiver server comes up by picking any 2 hop
    # host as client.
    waitListening(hosts_2hop[0], receiver, port)

    # Start flows from 2 hop hosts.
    for host in hosts_2hop:
        for i in xrange(n_2hops):
            host.cmd('iperf -Z bic -c %s -p %s -t %d -i 1 -yc >'
                     ' %s/iperf_%s.%d.txt &' % (
                    receiver.IP(), 5001, seconds, args.dir, str(host), i))
    for host in hosts_6hop:
        for i in xrange(n_6hops):
            host.cmd('iperf -Z bic -c %s -p %s -t %d -i 1 -yc >'
                     ' %s/iperf_%s.%d.txt &' % (
                    receiver.IP(), 5001, seconds, args.dir, str(host), i))

    # TODO(bhelsley): intelligent wait to detect when client iperf processes
    # have exited.
    sleep(seconds + 5)

    print 'Ending flows...'
    receiver.cmd('kill %iperf')

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

def check_bandwidth(net, test_rate='100M'):
  """Verify link bandwidth using iperf between hosts, and host to receiver."""

  parse_mbps_re = re.compile(r'(\d+\.?\d+) Mbits/sec')

  def _GetIPerfResult(*args, **kwargs):
      result = net.iperf(*args, **kwargs)
      cmbps = parse_mbps_re.match(result[-1])
      smbps = parse_mbps_re.match(result[-2])
      if not cmbps or not smbps:
          print '*** Error: cannot parse iperf result: %s' % result
          return (None, None)
      server_mbps = float(smbps.groups()[0])
      client_mbps = float(cmbps.groups()[0])
      return (server_mbps, client_mbps)

  # Measure the bandwidth between each pair of hosts in the topology.
  result = {}
  for i, h1 in enumerate(net.hosts):
    for h2 in net.hosts[i+1:]:
      server_mbps, client_mbps = _GetIPerfResult(
          [h1, h2], l4Type='UDP', udpBw=test_rate)
      result[('%s@%s' % (str(h1), h1.IP()), '%s@%s' % (str(h2), h2.IP()))] = (
          client_mbps, server_mbps)

  return result

def run_single_switch_outcast(net):
    recvr = net.getNodeByName('h0')
    h1 = net.getNodeByName('h1')
    h2 = net.getNodeByName('h2')
    run_outcast(net, recvr, [h1], [h2], n_2hops=args.n1, n_6hops=args.n2,
                rto_min=args.rto_min, queue_size=args.queue_size)


def main():
    "Create and run experiment"
    start = time()

    topo = SingleSwitchOutcastTopo()

    host = custom(CPULimitedHost, cpu=.15)  # 15% of system bandwidth
    # TODO(bhelsley): can max_queue_size be used to set the queues instead of
    # later running the "tc qdisc ..." command?
    link = custom(TCLink, bw=args.bw, delay='1ms',
                  max_queue_size=200)

    net = Mininet(topo=topo, host=host, link=link,
                  controller=RemoteController)

    net.start()

    cprint("*** Dumping network connections:", "green")
    dumpNetConnections(net)

    cprint("*** Testing connectivity", "blue")

    net.pingAll()

    cprint("*** Testing bandwidth", "blue")
    for pair, result in check_bandwidth(net, test_rate=('%sM' % args.bw)).iteritems():
      print pair, '=', result

    cprint("*** Running experiment", "magenta")
    run_single_switch_outcast(net)

    net.stop()
    end = time()
    os.system("killall -9 bwm-ng")
    cprint("Experiment took %.3f seconds" % (end - start), "yellow")

if __name__ == '__main__':
    check_prereqs()
    main()

