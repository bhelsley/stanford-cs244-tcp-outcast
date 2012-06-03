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
from ripl.ripl.dctopo import FatTreeTopo

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
                    default='11')

parser.add_argument('--time', '-t',
                    dest="time",
                    type=int,
                    help="Duration of the experiment.",
                    default=60)

parser.add_argument('--bw', '-b',
                    type=float,
                    help="Bandwidth of network links (in Mbps)",
                    default=10)

parser.add_argument('--ft',
                    type=bool,
                    help="Whether to experiment on FatTreeTopology",
                    default=False)

parser.add_argument('--iperf',
                    dest="iperf",
                    help="Path to custom iperf",
                    default='/usr/bin/iperf')

parser.add_argument('--impatient',
                    type=bool,
                    default=False)

# Expt parameters
args = parser.parse_args()

CUSTOM_IPERF_PATH = args.iperf
assert(os.path.exists(CUSTOM_IPERF_PATH))

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

    self.add_link(h0, s0, port1=0, port2=1, **lconfig)
    self.add_link(h1, s0, port1=0, port2=2, **lconfig)
    self.add_link(h2, s0, port1=0, port2=3, **lconfig)



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
    os.system("rmmod tcp_probe 1> /dev/null 2>&1; "
              "modprobe tcp_probe full=1 port=5001 bufsize=10240")
    Popen("cat /proc/net/tcpprobe > %s/tcp_probe.txt" % args.dir, shell=True)

def stop_tcpprobe():
    os.system("killall -9 cat; rmmod tcp_probe")

def start_tcpdump(iface):
    Popen("tcpdump -n -S -i %s > %s/tcp_dump.%s.txt" % (iface, args.dir, iface),
          shell=True)

# TODO(bhelsley): Ideally we should use a custom interface class, but my
# attempts to do this hit some strange python voodoo.
def configure_tbf_queue(iface, bw_mbps, queue_size_bytes):
  # First, clear any existing config on the interface
  cmds = ['tc qdisc del dev %s root' % iface]

  # Need to divide by HZ on host... EC2 uses 100.
  burst = float(bw_mbps) / 100
  # TODO(bhelsley): Avoiding setting peak rate and minburst, which means
  # when tokens are available we send as fast as possible.  Seems that
  # limiting this to values in the range we want (~100Mbps) is tricky.  Hoping
  # that configuring the bucket size for tokens is sufficient.
  cmds.append(
      'tc qdisc add dev %s root tbf rate %smbit '
      'burst %smbit limit %s' % (iface, bw_mbps, burst, queue_size_bytes))
  for cmd in cmds:
    print cmd
    print iface, os.system(cmd)


def run_outcast(net, receiver, hosts_2hop, hosts_6hop, n_2hops, n_6hops,
                tcpdump_ifaces, rto_min, queue_size, bw):
    """Run outcast experiment.

    Args:
      receiver: the receiver node.
      hosts_2hop: a list of host node objects for host nodes
                  at 2 hops from receiver sending data to receiver.
      hosts_6hop: a list of host node objects for host nodes
                  at 6 hops from receiver sending data to receiver.
      n_2hops: number of flows per 2-hop host.
      n_6hops: number of flows per 6-hop host.
      tcpdump_ifaces: A list of interfaces to monitor with tcpdump, identified by
                      the switch along with the interface connected to the receiver
      rto_min: RTO min time setting for each host as string.
      queue_size: Queue size of each switch.
      bw: Bandwidth of links in Mbps
    """

    seconds = args.time

    print 'Setting minRTO to %s on each host...' % rto_min
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

    # Start the receiver
    port = 5001
    receiver.cmd('%s -s -p' % CUSTOM_IPERF_PATH, port,
                 '> %s/iperf_server.txt' % args.dir, '&')

    # Wait till the receiver server comes up by picking any 2 hop
    # host as client.
    waitListening(hosts_2hop[0], receiver, port)

    # Start the bandwidth and cwnd monitors in the background
    monitor = Process(target=monitor_devs_ng,
                      args=('%s/bwm.txt' % args.dir, 1.0))
    monitor.start()
    start_tcpprobe()

    for iface in tcpdump_ifaces:
      start_tcpdump(iface)

    # Wait for tcpdump to start
    sleep(5)

    print 'Starting flows...'

    # Start flows from 2 hop hosts.
    for host in hosts_2hop:
        for i in xrange(n_2hops):
            host.cmd('%s -Z bic -c %s -p %s -t %d -i 1 -yc >'
                     ' %s/iperf_%s.%d.txt &' % (
                    CUSTOM_IPERF_PATH, receiver.IP(), 5001, seconds,
                    args.dir, str(host), i))
    for host in hosts_6hop:
        for i in xrange(n_6hops):
            host.cmd('%s -Z bic -c %s -p %s -t %d -i 1 -yc >'
                     ' %s/iperf_%s.%d.txt &' % (
                    CUSTOM_IPERF_PATH, receiver.IP(), 5001, seconds,
                    args.dir, str(host), i))

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

def check_bandwidth(net, test_rate='100M', total_hosts=16):
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
  num_hosts = 0
  for i, h1 in enumerate(net.hosts):
      for h2 in net.hosts[i+1:]:
          if num_hosts > total_hosts:
              break
          num_hosts += 1
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
                tcpdump_ifaces=['s0-eth1', 's0-eth2', 's0-eth3'],
                rto_min=args.rto_min,
                queue_size=args.queue_size,
                bw=args.bw)

def fat_tree_get_6hop_nodes(net, topo, host_name):
    """Returns all 6 hop nodes from host."""
    host_pod = topo.id_gen(name=host_name).pod

    hosts_6hop = []
    for node in topo.layer_nodes(FatTreeTopo.LAYER_HOST):
        node_pod = topo.id_gen(name=node).pod
        if host_pod != node_pod:
            hosts_6hop.append(net.getNodeByName(node))

    return hosts_6hop

def run_fat_tree_outcast(net):
    recvr = net.getNodeByName('0_0_2')
    hosts_2hop = [net.getNodeByName('0_0_3')]
    hosts_6hop = fat_tree_get_6hop_nodes(net, net.topo, '0_0_2')
    if args.n2 < len(hosts_6hop):
        n_6hops = 1
        hosts_6hop = hosts_6hop[:args.n2]
    else:
        n_6hops = int(args.n2 / len(hosts_6hop))

    run_outcast(net, recvr, hosts_2hop, hosts_6hop, n_2hops=args.n1,
                n_6hops=n_6hops,
                tcpdump_ifaces=['0_0_1-eth2', '0_0_1-eth1', '0_0_1-eth3', '0_0_1-eth4'],
                rto_min=args.rto_min,
                queue_size=args.queue_size,
                bw=args.bw)


def main():
    "Create and run experiment"
    start = time()

    if args.ft:
        topo = FatTreeTopo(4)
    else:
        topo = SingleSwitchOutcastTopo()

    host = custom(CPULimitedHost, cpu=1)
    link = custom(TCLink, bw=args.bw, delay='0ms')

    net = Mininet(topo=topo, host=host, link=link)

    net.start()

    print 'Setting queue size to %s for all switches...' % args.queue_size
    for s in net.switches:
      for intf in s.intfNames():
        if intf == 'lo':
            continue
        #cmd = ("tc qdisc change dev %s parent 1:1 "
        #       "handle 10: netem limit %s" % (intf, queue_size))
        #print '  %s' % intf, os.system(cmd)
        configure_tbf_queue(intf, args.bw, args.queue_size)


    cprint("*** Dumping network connections:", "green")
    dumpNetConnections(net)

    cprint("*** Testing connectivity", "blue")

    net.pingAll()

    cprint("*** Testing bandwidth", "blue")
    if not args.impatient:
      for pair, result in check_bandwidth(net, test_rate=('%sM' % args.bw)).iteritems():
        print pair, '=', result
    else:
      print '  skipped'

    cprint("*** Running experiment", "magenta")
    if args.ft:
        run_fat_tree_outcast(net)
    else:
        run_single_switch_outcast(net)

    net.stop()
    end = time()
    os.system("killall -9 bwm-ng")
    cprint("Experiment took %.3f seconds" % (end - start), "yellow")

if __name__ == '__main__':
    check_prereqs()
    main()

