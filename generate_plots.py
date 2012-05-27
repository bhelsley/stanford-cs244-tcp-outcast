import sys
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
    # TODO(bhelsley): I'm swapping sender and receiver here.  The only TCP probe documentation
    # I can find claims the opposite:
    #  http://www.linuxfoundation.org/collaborate/workgroups/networking/tcptesting
    # BUT, the packets in the tcp_dump with the iperf server as the receiver are 32-byte ACKs.
    # Not sure if there's something about the tcp_probe module that might cause this to get
    # confused?
    (ts, receiver, sender, pkt_bytes, next_seqno, unacked_seqno, cwnd,
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


def ComputeMbps(tcp_probe_records, bucket_size_ms, end_time_ms):
  """Compute approximate Mbps series from a list of TcpProbeRecords."""
  buckets = {}
  for r in tcp_probe_records:
    bucket = int(r.timestamp * 1000 / bucket_size_ms)
    buckets.setdefault(bucket, 0)
    buckets[bucket] += (8 * r.pkt_bytes)

  max_bucket = int(float(end_time_ms) / bucket_size_ms)
  one_mbps = float(2**20) / 1000 * bucket_size_ms
  r = [buckets.get(x, 0) / one_mbps for x in xrange(max_bucket)]
  return r

def MakeFig(rows, cols):
  height = 4 * rows
  width = 6 * cols
  matplotlib.rc('figure', figsize=(width, height))
  fig = matplotlib.pyplot.figure()
  return fig

def PlotMbpsInstant(ax, tcp_probe_data, bucket_size_ms, end_time_ms, title,
                    outcast_host):
  to_plot = []
  for key, values in tcp_probe_data.iteritems():
    mbps = ComputeMbps(values, bucket_size_ms, end_time_ms)
    to_plot.append((sorted(mbps)[int(0.7 * len(mbps))], key, mbps))
  shift = max([x[0] for x in to_plot]) * 1.5
  y_adjust = 0
  lines = []
  for _, key, mbps in sorted(to_plot):
    label = None
    if key.startswith(outcast_host):
      label = key
    l = ax.plot([y + y_adjust for y in mbps], lw=2, label=label)[0]
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
  if title:
    ax.set_title(title)


def _GetMeanMedian(l):
  l = sorted(l)
  if l:
    return (sum(l) / float(len(l)), l[len(l)/2])
  return None


def PlotMbpsSummary(ax, tcp_probe_data, bucket_size_ms, end_time_ms, title=None):
  # Aggregate tcp_probe data by host (to delineate number of flows).
  # Compute mean and median for first, middle, and last third.
  host_data = {}
  for key, values in tcp_probe_data.iteritems():
    host = key.split(':')[0]
    mbps = ComputeMbps(values, bucket_size_ms, end_time_ms)
    first, middle, last = host_data.setdefault(host, ([], [], []))
    n = len(mbps)
    first.extend(mbps[:n/3])
    middle.extend(mbps[n/3:2*n/3])
    last.extend(mbps[2*n/3:])
  means = {}
  for h, data in host_data.iteritems():
    first, middle, last = data
    means[h] = [_GetMeanMedian(first)[0],
                _GetMeanMedian(middle)[0],
                _GetMeanMedian(last)[0]]

  ind = range(3)
  width = 0.35
  rects1 = ax.bar(ind, means['10.0.0.2'], width, color='r')
  rects2 = ax.bar([x + width for x in ind], means['10.0.0.3'], width, color='y')

  ax.set_ylabel('Avg Thpt (Mbps)')
  ax.set_xlabel('Time (sec)')
  ax.set_xticks([x + width for x in ind])
  ax.set_xticklabels(('0.1', '0.3', '0.5'))

  ax.legend((rects1[0], rects2[0]), ('10.0.0.2', '10.0.0.3'))
  if title:
    ax.set_title(title)


def main():
  parser = argparse.ArgumentParser()
  parser.add_argument('-f', dest='files', nargs='+', required=True)
  parser.add_argument('-r', dest='receiver', required=True)
  parser.add_argument('-o', dest='out', required=True)
  parser.add_argument('--instant_title', dest='instant_title')
  parser.add_argument('--summary_title', dest='summary_title')
  parser.add_argument('--skip_instant', dest='skip_instant', type=bool,
                      default=False)
  parser.add_argument('--bucket_size_ms', required=True, type=int)
  parser.add_argument('--end_time_ms', required=True, type=int)
  parser.add_argument('--outcast_host', default='10.0.0.2')
  args = parser.parse_args()

  for f in args.files:
    with open(f) as fd:
      data = ParseTcpProbe(fd, lambda(x): x.receiver == args.receiver)
      if not args.skip_instant:
        fig = MakeFig(1, 2)
        ax = fig.add_subplot(1, 2, 1)
        PlotMbpsInstant(ax, data, args.bucket_size_ms, args.end_time_ms, args.instant_title,
                        args.outcast_host)
        ax = fig.add_subplot(1, 2, 2)
        PlotMbpsSummary(ax, data, args.bucket_size_ms, args.end_time_ms, args.summary_title)
      else:
        fig = MakeFig(1, 1)
        ax = fig.add_subplot(1, 1, 1)
        PlotMbpsSummary(ax, data, args.bucket_size_ms, args.end_time_ms, args.summary_title)

      matplotlib.pyplot.savefig(args.out)


if __name__ == '__main__':
  main()

