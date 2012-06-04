
# Build ripl:
cd ripl
sudo python setup.py develop
cd -

# Build riplpox:
cd riplpox
sudo python setup.py develop
cd -

# Reset MPTCP parameters
sudo sysctl -w net.ipv4.tcp_dctcp_enable=0
sudo sysctl -w net.ipv4.tcp_ecn=0