import argparse
import generate_plots

from collections import deque

def print_queue(queue, record, packet_id, alias):
  # Queue simulation at outgoing s0-eth1 interface.
  event_type = record[8]
  egress_alias = record[9]
  ts = record[0]

  # Remove all packets which have left the queue
  while queue and queue[0][2] < ts:
    queue.popleft()

  if event_type == 'FOUND' and egress_alias == alias:
    ingress_ts = float(record[7])
    egress_ts = float(record[10])      
    queue.append((packet_id, ingress_ts, egress_ts))

  # print the queue.
  packets = [p[0] for p in queue]
  print '%s: %s' % (alias, packets)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', dest='files', required=True, action='append')
  parser.add_argument('-s', dest='switch_ip', required=True, action='append')
  args = parser.parse_args()

  if len(args.files) < 2:
    print 'Need dumps from at least one input and output port!'
    return

  switch_files = {}
  for f in args.files:
    try:
      alias, filename = f.split('=')
      switch_files[alias] = filename
    except ValueError:
      print 'Bad files passed in.  Format is -f <alias>=<path to file>.'

  swiface_ip_map = {}
  for entry in args.switch_ip:
    try:
      alias, ip = entry.split('=')
      swiface_ip_map[alias] = ip
    except ValueError:
      print 'Bad IP address passed for a switch. Format is -s <alias>=<IP>.'

  first_ts = [None]
  join = {}
  for alias, filename in switch_files.iteritems():
    with open(filename) as fd:
      data = generate_plots.ParseTcpDump(fd, first_ts=first_ts)
      for records in data.itervalues():
        for r in records:
          key = r.original_data.split(' ')[1:]
          key = ' '.join(key)
          ts = float(r.timestamp) * 1000
          join.setdefault(key, []).append((r, ts, alias))

  records = []
  for key, v in join.iteritems():
    v.sort(key=lambda x: x[1], reverse=True)
    #print key, v
    while v:
      record, ts, src = v.pop()

      ingress_alias = ''
      ingress_ts = ''
      egress_alias = ''
      egress_ts = ''

      sender_ip, _ = record.sender.split(':')
      receiver_ip, _ = record.receiver.split(':')

      if swiface_ip_map.get(src) == sender_ip:
        ingress_alias = src
        ingress_ts = '%f' % ts
      elif swiface_ip_map.get(src) == receiver_ip:
        egress_alias = src
        egress_ts = '%f' % ts

      if not v:
        event_type = 'DROP'
        if not ingress_alias:
          ingress_alias = src
          ingress_ts = '%f' % ts
      else:
        _, ts_next, src_next = v[-1]
        
        if src_next == src:
          event_type = 'UNKNOWN'
        else:
          if not ingress_alias:
            ingress_alias = src
            ingress_ts = '%f' % ts
          egress_alias = src_next
          egress_ts = '%f' % ts_next
          event_type = 'FOUND'
          v.pop()
      records.append((ts, record.sender, record.receiver, record.pkt_type,
                      record.seqno, record.pkt_bytes, ingress_alias,
                      ingress_ts, event_type, egress_alias, egress_ts))

  records.sort()

  queues = {}
  for alias in switch_files.iterkeys():
    queues.setdefault(alias, deque())

  if records:
    print ('#0.packet_id,1.sender,2.receiver,3.pkt_type,4.seqno,5.pkt_bytes,'
           '6.ingress_alias,7.ingress_ts,8.event_type,9.egress_alias,'
           '10.egress_ts')
    perflow_packet_ids = {}
    for r in records:
      sender = r[1]
      receiver = r[2]
      key = (r[1], r[2])
      packet_id = perflow_packet_ids.setdefault(key, 1)
      sender_id = sender.split('.')[-1]
      pid = '%s-%d' % (sender_id, packet_id)

      print ('%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s' % (
        pid, r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10]))

      for alias, queue in queues.iteritems():
        print_queue(queue, r, pid, alias)
      print ''

      perflow_packet_ids[key] += 1


if __name__ == '__main__':
  main()

