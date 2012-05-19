import argparse
import collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot


TcpProbeRecord = collections.namedtuple(
    'TcpProbeRecord',
    ['timestamp', 'sender', 'receiver', 'pkt_bytes', 'next_seqno',
     'unacked_seqno', 'cwnd', 'slow_start_threshold', 'send_window'])


def ParseTcpProbe(fd, filter_fn=None):
  """Parse TCP probe output from file-like object.
  
  Args:
    fd: File-like object to read from.
  """

  def _ParseLine(l):
    # tcp_probe files have the following format:
    # <timestamp_secs> <sender> <receiver> <pkt_bytes> <next_seqno>
    #    <unacked_seqno> <cwnd> <slow_start_threshold> <send_window> <???>
    #
    # sample:
    # 2.221032535 10.0.0.2:39815 10.0.0.1:5001 32 0x1a2a710c 0x1a2a387c 11 2147483647 14592 85
    tokens = l.split(' ')
    if len(tokens) != 10:
      return
    (ts, sender, receiver, pkt_bytes, next_seqno, unacked_seqno, cwnd,
     slow_start_threshold, send_window, _) = tokens
    return TcpProbeRecord(float(ts), sender, receiver, int(pkt_bytes),
                          int(next_seqno, 16), int(unacked_seqno, 16), int(cwnd),
                          int(slow_start_threshold), int(send_window))

  result = {}
  for l in fd:
    r = _ParseLine(l)
    if not r or (filter_fn and not filter_fn(r)):
      continue
    flow_id = '%s-%s' % (r.sender, r.receiver)
    result.setdefault(flow_id, []).append(r)

  return result


def ComputeMbps(tcp_probe_records):
  """Compute approximate Mbps series from a list of TcpProbeRecords."""
  buckets = {}
  for r in tcp_probe_records:
    bucket = int(r.timestamp)
    buckets.setdefault(bucket, 0)
    buckets[bucket] += (8 * r.pkt_bytes)

  max_bucket = max(buckets.iterkeys())
  one_mb = float(2**20)
  return [buckets.get(x, 0) / one_mb for x in xrange(max_bucket + 1)]


def PlotMbps(tcp_probe_data, outfile):
  matplotlib.rc('figure', figsize=(16, 6))
  fig = matplotlib.pyplot.figure()
  ax = fig.add_subplot(1, 1, 1)
  to_plot = []
  for key, values in tcp_probe_data.iteritems():
    mbps = ComputeMbps(values)
    to_plot.append((sum(mbps) / len(mbps), key, mbps))
  shift = max([x[0] for x in to_plot]) * 1.5
  y_adjust = 0
  lines = []
  for _, key, mbps in sorted(to_plot):
    l = ax.plot([y + y_adjust for y in mbps], lw=2, label=key)[0]
    lines.append((l.get_color(), y_adjust, mbps))
    y_adjust += shift
  # Fill-in the plots in reverse order (so we overlap front-to-back).
  for c, y_adjust, mbps in reversed(lines):
    ax.fill_between(xrange(len(mbps)), [y + y_adjust for y in mbps],
                    y2=y_adjust, color=c)

  ax.grid(True)
  ax.legend()
  ax.set_xlabel("seconds")
  ax.set_ylabel("Mbps")

  matplotlib.pyplot.savefig(outfile)
    
     
def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', dest='files', nargs='+', required=True)
  parser.add_argument('-r', dest='receiver', required=True)
  parser.add_argument('-o', dest='out', required=True)
  args = parser.parse_args()

  for f in args.files:
    with open(f) as fd:
      data = ParseTcpProbe(fd, lambda(x): x.receiver == args.receiver)    
      PlotMbps(data, args.out)


if __name__ == '__main__':
  main()

