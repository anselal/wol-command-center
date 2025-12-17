## To make it permanent (survive reboots):

1. Run `echo 'net.ipv4.ping_group_range = 0 2147483647' | sudo tee -a /etc/sysctl.conf`
2. Run `sudo sysctl -p`