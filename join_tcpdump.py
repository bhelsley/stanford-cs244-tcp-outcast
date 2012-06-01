import argparse
import generate_plots

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', dest='files', required=True, action='append')
  parser.add_argument('-s', dest='switch_ip', required=True, action='append')
  args = parser.parse_args()

  if len(args.files) < 2:
    print 'Need dumps from at least one input and output port!'
    return

  for f in args.files:
    try:
      alias, filename = f.split('=')
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
  for f in args.files:
    alias, filename = f.split('=')
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

      if swiface_ip_map[src] == sender_ip:
        ingress_alias = src
        ingress_ts = '%f' % ts
      elif swiface_ip_map[src] == receiver_ip:
        egress_alias = src
        egress_ts = '%f' % ts

      if not v:
        event_type = 'DROP'
      else:
        _, ts_next, src_next = v[-1]
        if not ingress_alias:
          ingress_alias = 'empty'
        
        if src_next == src:
          event_type = 'UNKNOWN'
        else:
          egress_alias = src_next
          egress_ts = '%f' % ts_next
          event_type = 'FOUND'
          v.pop()
      records.append((ts, '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s' % (
            record.sender, record.receiver, record.pkt_type, record.seqno,
            record.pkt_bytes, ingress_alias, ingress_ts, event_type,
            egress_alias, egress_ts)))

  records.sort()
  if records:
    print ('#1.sender,2.receiver,3.pkt_type,4.seqno,5.pkt_bytes,'
           '6.ingress_alias,7.ingress_ts,8.event_type,9.egress_alias,'
           '10.egress_ts')
    for _, line in records:
      print line


if __name__ == '__main__':
  main()

