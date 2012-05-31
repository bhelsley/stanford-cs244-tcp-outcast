import argparse
import generate_plots

def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', dest='files', required=True, action='append')
  args = parser.parse_args()

  if len(args.files) < 2:
    print 'Need dumps from at least one input and output port!'
    return

  for f in args.files:
    try:
      alias, filename = f.split('=')
    except ValueError:
      print 'Bad files passed in.  Format is -f <alias>=<path to file>.'

  first_ts = [None]
  join = {}
  for f in args.files:
    alias, filename = f.split('=')
    with open(filename) as fd:
      data = generate_plots.ParseTcpDump(fd, first_ts=first_ts)
      for records in data.itervalues():
        for r in records:
          key = '%s,%s,%s,%s,%s' % (r.sender, r.receiver, r.pkt_type,
                                    r.seqno, r.pkt_bytes)
          join.setdefault(key, []).append((r.timestamp, alias))

  records = []
  for key, v in join.iteritems():
    v.sort(reverse=True)
    while v:
      ts, src = v.pop()
      if not v:
        records.append((ts, '%s,%s,%s,UNKNOWN,,' % (key, src, ts)))
        continue
      ts_next, src_next = v[-1]
      if src_next == src:
        records.append((ts, '%s,%s,%s,DROP,,' % (key, src, ts)))
      else:
        records.append((ts, '%s,%s,%s,FOUND,%s,%s' % (
             key, src, ts, src_next, ts_next)))
        v.pop()

  records.sort()
  if records:
    print ('#1.sender,2.receiver,3.pkt_type,4.seqno,5.pkt_bytes,'
           '6.ingress_alias,7.ingress_ts,8.event_type,9.egress_alias,'
           '10.egress_ts')
    for _, line in records:
      print line


if __name__ == '__main__':
  main()

