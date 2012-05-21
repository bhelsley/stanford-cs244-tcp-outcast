#!/usr/bin/python

"""CS244 PA3: Fat Tree Topology
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.util import custom, dumpNetConnections
from mininet.log import lg, output
from mininet.cli import CLI

lg.setLogLevel('info')


class FatTreeTopo(Topo):

    def __init__(self, bw, delay=None, **params):
        """Fat Tree topology with 4-ports switches and 3 layers.
           k: number of ports in each switch
           bw: bandwidth of each link in Mb/s
           delay: link delay (e.g. 1ms)"""
        Topo.__init__(self, **params)

        self._bw = bw
        self._delay = delay

        self._k = 4
        self._num_tors = 8
        self._num_agg_switches = 8
        self._num_core_switches = 4
        self._num_hosts = 16

        self._hosts = []
        self._tors = []
        self._agg_switches = []
        self._core_switches = []

        self._CreateTopology()

    def _CreateTopology(self):
        # Create the hosts
        for i in range(self._num_hosts):
            self._hosts.append(self.add_host('h%d' % (i + 1)))

        # Create the switches
        count = 1
        for i in range(self._num_tors):
            self._tors.append(self.add_switch('s%d' % (i + 1)))
        count += self._num_tors

        for i in range(self._num_agg_switches):
            self._agg_switches.append(self.add_switch('a%d' % (i + 1)))
        count += self._num_agg_switches

        for i in range(self._num_core_switches):
            self._core_switches.append(self.add_switch('c%d' % (i + 1)))

        # Add links between hosts and the TOR switches.
        for i in range(self._num_tors):
            self.add_link(self._hosts[2*i], self._tors[i], bw=self._bw,
                          delay=self._delay, use_htb=True)
            self.add_link(self._hosts[2*i + 1], self._tors[i], bw=self._bw,
                          delay=self._delay, use_htb=True)

        # Add links between ToR and Aggregate switches.
        for i in range(self._num_tors):
            for j in range(self._k / 2):
                pod_num = int(i / (self._k / 2))
                agg_switch = self._agg_switches[self._k / 2 * pod_num + j]
                self.add_link(self._tors[i], agg_switch, bw=self._bw,
                              delay=self._delay, use_htb=True)

        # Add links between core switches and aggregate switches.
        for i in range(self._num_core_switches):
            for j in range(self._k):
                start_switch = int(i / (self._k / 2))
                agg_switch = self._agg_switches[start_switch + j * self._k / 2]
                self.add_link(self._core_switches[i], agg_switch,
                              bw=self._bw, delay=self._delay, use_htb=True)


def main():
    topo = FatTreeTopo(bw=1000, delay='0.1ms')

    host = custom(CPULimitedHost, cpu=0.5)

    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink)
    net.start()

    dumpNetConnections(net)
    #net.pingAll()
    CLI(net)

    net.stop

if __name__ == '__main__':
    main()
