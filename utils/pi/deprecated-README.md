These are a bunch of deprecated steps to do various things.

## [Setup local docker registry](https://www.allisonthackston.com/articles/local-docker-registry.html)

Speeds up pulling docker images onto the Jetsons and prevents double space usage trying
to move compressed images to their destinations.

```
docker run -d -p 5000:5000 --restart always --name registry registry:2
```

Add the following to `/etc/docker/daemon.json` for both the server and client:

```
{ 
    "insecure-registries": ["your_hostname.local:5000"] 
}
```

`your_hostname.local` can also be a static IP address.

Push a local docker image:

```
docker tag your_docker_image your_hostname.local:5000/your_docker_image
docker push your_hostname.local:5000/your_docker_image
```

Then, you can pull as such:
```
docker pull your_hostname.local:5000/your_docker_image
```

## \[Test setup\] WiFi to Ethernet Bridging

```bash
sudo apt-get install iptables-persistent
```

Setup dhcpcd:
```bash
sudoedit /etc/dhcpcd.conf`
```

Add the following at the bottom:
```
interface eth0
static routers=192.168.1.1
static ip_address=192.168.1.1/24
nohook wpa_supplicant
```

Restart static IP:
```bash
sudo systemctl restart dhcpcd
```

Setup ip forwarding:
```bash
sudoedit /etc/sysctl.conf
```
Uncomment the respective part:
```
net.ipv4.ip_forward=1
```
Run immediately:
```bash
sudo sh -c "echo 1 > /proc/sys/net/ipv4/ip_forward"
```

Run iptable rules:
```bash
sudo iptables -t nat -A POSTROUTING -o wlan0 -j MASQUERADE
sudo iptables -A FORWARD -i wlan0 -o eth0 -m state --state RELATED,ESTABLISHED -j ACCEPT  
sudo iptables -A FORWARD -i eth0 -o wlan0 -j ACCEPT
sudo netfilter-persistent save
```

Once done, reboot.

When finished testing, make sure to delete the rules in
`/etc/iptables/rules.v4` and not use the `192.168.1.1` gateway.


## \[Deprecated\] Raspberry Pi Recording Setup

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
static ip_address=192.168.10.1/24
```

Then, reboot:
```
sudo reboot
```

