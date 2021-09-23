# Raspberry Pi utils

The service file and cam.sh script runs FFMPEG to record the RTSP
videos from the IP Cameras that are deployed.

## Raspberry Pi Recording Setup

Add the following to `sudo crontab -e`
```
0 0 * * * systemctl restart cam-record.service
```

If you have more than one recording with the same setup just add more services
to the end, eg.

```
0 0 * * * systemctl restart cam-record.service cam-record-up.service
```

## Raspberry Pi DHCP

Adapted from [this tutorial](https://www.itsfullofstars.de/2019/02/dhcp-server-on-linux-with-raspberry-pi/).

To run a DHCP server on the Raspberry Pi use this package:

```
sudo apt install isc-dhcp-server
```

This installs a service that acts as the server. Check the status as such:
```
sudo systemctl status isc-dhcp-server.service
```

Configure parameters at
```
sudoedit /etc/dhcp/dhcpd.conf
```

Activate:
```
# If this DHCP server is the official DHCP server for the local
# network, the authoritative directive should be uncommented.
authoritative;
```

Subnet IP addresses:

```
subnet 192.168.10.0 netmask 255.255.255.0 {
  range 192.168.10.150 192.168.10.240;
  option routers 192.168.10.1;
  option domain-name-servers 8.8.8.8, 8.8.4.4;
}
```

You must change your Pi's IP address to the network IP:
```
sudoedit /etc/dhcpcd.conf
```

Add or edit the following:
```
interface eth0
static ip_address=192.168.10.0/24
static routers=192.168.10.1
static domain_name_servers=192.168.10.1
```

Then, reboot:
```
sudo reboot
```
