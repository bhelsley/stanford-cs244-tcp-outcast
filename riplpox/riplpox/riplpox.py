"""
RipL+POX.  As simple a data center controller as possible.
"""

from pox.core import core
from pox.lib.util import dpidToStr
import pox.openflow.libopenflow_01 as of
from pox.lib.revent import EventMixin

from ripl.mn import topos

from util import buildTopo, getRouting

log = core.getLogger()

# Number of bytes to send for packet_ins
MISS_SEND_LEN = 2000


# Borrowed from pox/forwarding/l2_multi
class Switch (EventMixin):
  def __init__ (self):
    self.connection = None
    self.ports = None
    self.dpid = None
    self._listeners = None

  def __repr__ (self):
    return dpidToStr(self.dpid)

  def disconnect (self):
    if self.connection is not None:
      log.debug("Disconnect %s" % (self.connection,))
      self.connection.removeListeners(self._listeners)
      self.connection = None
      self._listeners = None

  def connect (self, connection):
    if self.dpid is None:
      self.dpid = connection.dpid
    assert self.dpid == connection.dpid
    if self.ports is None:
      self.ports = connection.features.ports
    self.disconnect()
    log.debug("Connect %s" % (connection,))
    self.connection = connection
    self._listeners = self.listenTo(connection)

  def send_packet_data(self, outport, data = None):
    msg = of.ofp_packet_out(in_port=of.OFPP_NONE, data = data)
    msg.actions.append(of.ofp_action_output(port = outport))
    self.connection.send(msg)

  def send_packet_bufid(self, outport, buffer_id = -1):
    msg = of.ofp_packet_out(in_port=of.OFPP_NONE)
    msg.actions.append(of.ofp_action_output(port = outport))
    msg.buffer_id = buffer_id
    self.connection.send(msg)

  def install(self, port, match, buf = -1):
    msg = of.ofp_flow_mod()
    msg.match = match
    msg.idle_timeout = 20
    msg.hard_timeout = 60
    msg.actions.append(of.ofp_action_output(port = port))
    msg.buffer_id = buf
    self.connection.send(msg)

  def _handle_ConnectionDown (self, event):
    self.disconnect()
    pass


class RipLController(EventMixin):

  def __init__ (self, t, r):
    self.switches = {}  # Switches seen: [dpid] -> Switch
    self.t = t  # Master Topo object, passed in and never modified.
    self.r = r  # Master Routing object, passed in and reused.
    self.macTable = {}  # [mac] -> (dpid, port)

    # TODO: generalize all_switches_up to a more general state machine.
    self.all_switches_up = False  # Sequences event handling.
    self.listenTo(core.openflow, priority=0)

  def _raw_dpids(self, arr):
    "Convert a list of name strings (from Topo object) to numbers."
    return [self.t.id_gen(name = a).dpid for a in arr]

  def _install_path(self, event, out_dpid, final_out_port, packet):
    "Install entries on route between two switches."
    in_name = self.t.id_gen(dpid = event.dpid).name_str()
    out_name = self.t.id_gen(dpid = out_dpid).name_str()
    route = self.r.get_route(in_name, out_name, out_port=final_out_port)
    log.info("route from src: %s to dst %s: %s" % (packet.src, packet.dst, route))
    match = of.ofp_match.from_packet(packet)
    for i, node in enumerate(route):
      node_dpid = self.t.id_gen(name = node).dpid
      if i < len(route) - 1:
        next_node = route[i + 1]
        out_port, next_in_port = self.t.port(node, next_node)
      else:
        out_port = final_out_port
      self.switches[node_dpid].install(out_port, match)

  def _handle_PacketIn(self, event):
    #log.info("Parsing PacketIn.")
    if not self.all_switches_up:
      log.info("Saw PacketIn before all switches were up - ignoring.")
      return
    else:
      packet = event.parsed
      dpid = event.dpid
      #log.info("PacketIn: %s" % packet)
      in_port = event.port
      t = self.t

      in_sw = self.t.id_gen(dpid=dpid)
      # Learn MAC address of the sender on every packet-in for only EDGE switches.
      if in_sw.pod != 4 and (in_sw.sw == 0 or in_sw.sw == 1) and (in_port == 2 or in_port == 4):
        self.macTable[packet.src] = (dpid, in_port)
  
      #log.info("mactable: %s" % self.macTable)
  
      # Insert flow, deliver packet directly to destination.
      if packet.dst in self.macTable:
        out_dpid, out_port = self.macTable[packet.dst]
        try:
          self._install_path(event, out_dpid, out_port, packet)
        except Exception as e:
          log.info('event = %s, out_dpid = %s, out_port = %s, packet = %s' % (event, out_dpid, out_port, packet))
          raise e

        #log.info("sending to entry in mactable: %s %s" % (out_dpid, out_port))
        self.switches[out_dpid].send_packet_data(out_port, event.data)

      else:
        # Broadcast to every output port except the input on the input switch.
        # Hub behavior, baby!
        for sw in self._raw_dpids(t.layer_nodes(t.LAYER_EDGE)):
          #log.info("considering sw %s" % sw)
          ports = []
          sw_name = t.id_gen(dpid = sw).name_str()
          for host in t.down_nodes(sw_name):
            sw_port, host_port = t.port(sw_name, host)
            if sw != dpid or (sw == dpid and in_port != sw_port):
              ports.append(sw_port)
          # Send packet out each non-input host port
          # TODO: send one packet only.
          for port in ports:
            #log.info("sending to port %s on switch %s" % (port, sw))
            #buffer_id = event.ofp.buffer_id
            #if sw == dpid:
            #  self.switches[sw].send_packet_bufid(port, event.ofp.buffer_id)
            #else:
            self.switches[sw].send_packet_data(port, event.data)
            #  buffer_id = -1


  def _handle_ConnectionUp (self, event):
    sw = self.switches.get(event.dpid)
    sw_str = dpidToStr(event.dpid)
    log.info("Saw switch come up: %s", sw_str)
    name_str = self.t.id_gen(dpid = event.dpid).name_str()
    if name_str not in self.t.switches():
      log.warn("Ignoring unknown switch %s" % sw_str)
      return
    if sw is None:
      log.info("Added fresh switch %s" % sw_str)
      sw = Switch()
      self.switches[event.dpid] = sw
      sw.connect(event.connection)
    else:
      log.info("Odd - already saw switch %s come up" % sw_str)
      sw.connect(event.connection)
    sw.connection.send(of.ofp_set_config(miss_send_len=MISS_SEND_LEN))

    if len(self.switches) == len(self.t.switches()):
      log.info("Woo!  All switches up")
      self.all_switches_up = True

  def _handle_ConnectionDown(self, event):
    sw_str = dpidToStr(event.dpid)
    log.info("Disconnecting switch: %s, %s", event.dpid, sw_str)
    sw = self.switches.pop(event.dpid, None)
    if sw is None:
      log.info('No such switch: %s', sw_str)
    else:
      self.all_switches_up = False
    

def launch(topo = None, routing = None):
  """
  Args in format toponame,arg1,arg2,...
  """
  # Instantiate a topo object from the passed-in file.
  if not topo:
    raise Exception("please specify topo and args on cmd line")
  else:
    t = buildTopo(topo, topos)
    r = getRouting(routing, t)

  core.registerNew(RipLController, t, r)

  log.info("RipL-POX running with topo=%s." % topo)
