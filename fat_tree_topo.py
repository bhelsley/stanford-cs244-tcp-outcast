#!/usr/bin/python

"""CS244 PA3: Fat Tree Topology
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost, RemoteController
from mininet.link import TCLink
from mininet.util import custom, dumpNetConnections
from mininet.log import lg, output
from mininet.cli import CLI
from ripl.ripl.dctopo import FatTreeTopo

lg.setLogLevel('info')


def main():
    topo = FatTreeTopo(4)

    host = custom(CPULimitedHost, cpu=0.5)

    net = Mininet(topo=topo, host=CPULimitedHost, link=TCLink,
                  controller=RemoteController)
    net.start()

    dumpNetConnections(net)
    #net.pingAll()
    CLI(net)

    net.stop()

if __name__ == '__main__':
    main()
