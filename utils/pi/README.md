# Raspberry Pi utils

***This has been tested on Raspberry Pi Buster.***

The service file and cam.sh script runs FFMPEG to record the RTSP
videos from the IP Cameras that are deployed.

Install `usbmount` to auto mount any USB devices that are plugged in:
```bash
sudo apt install usbmount
```

USB devices should be automatically mounted to `/media/usb[0-7]`.

If auto mounting NTFS filesystems is desired [this link should
help](https://raspberrypi.stackexchange.com/questions/41959/automount-various-usb-stick-file-systems-on-jessie-lite).
```bash
sudoedit /etc/udev/rules.d/usbmount.rules
```
Add the following rules:
```
KERNEL=="sd*", DRIVERS=="sbp2",         ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="sd*", SUBSYSTEMS=="usb",       ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="ub*", SUBSYSTEMS=="usb",       ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="sd*",                          ACTION=="remove",       RUN+="/usr/share/usbmount/usbmount remove"
KERNEL=="ub*",                          ACTION=="remove",       RUN+="/usr/share/usbmount/usbmount remove"
```

Then, create a systemd service:
```bash
sudoedit /etc/systemd/system/usbmount@.service
```
With the following contents:
```
[Unit]
BindTo=%i.device
After=%i.device

[Service]
Type=oneshot
TimeoutStartSec=0
Environment=DEVNAME=%I
ExecStart=/usr/share/usbmount/usbmount add
RemainAfterExit=yes
```

```bash
sudo systemctl edit systemd-udevd
```
Put the following:
```
[Service]
PrivateMounts=no
```

Then, reboot.

Create a new user to restrict ssh key usage:
- Setup a new user (eg. `lockeduser`)
- Create and give new user the `sshfs` group
- Put the contents of `sshfs.conf` into the bottom of `/etc/ssh/sshd_config`
- Add the contents of `revtunnel_id_rsa.pub` to the new user's `/home/lockeduser/.ssh/authorized_keys`

## Set Static IP

Get the gateway and DNS IP addresses of the current network:
```bash
ip r # Can find gateway
grep "nameserver" /etc/resolv.conf # Get DNS IP address (Likely the gateway)
```

Edit the following to setup static IP:
```bash
sudoedit /etc/dhcpcd.conf
```

Add the following at the bottom:
```
interface [INTERFACE]
static_routers=[ROUTER IP]
static domain_name_servers=[DNS IP]
static ip_address=[DESIRED STATIC IP ADDRESS]/24
```

The defaults for a Starlink router is the following:
```
interface eth0
static routers=192.168.1.1
static domain_name_servers=192.168.1.1 1.1.1.1 1.0.0.1 8.8.8.8
static ip_address=[STATIC IP ADDRESS YOU WANT]/24
```

## Streaming from RTSP to Amazon Kinesis Video Streams

Install dependecies:
```bash
sudo apt update && sudo apt upgrade && sudo apt install docker.io cmake
```

Add user to docker group and log out and log back in:
```bash
sudo usermod -aG docker $USER
```

For raspi 32-bit, AWS-CLIv2 is not officially supported,
so we will build it using Python. [First install Python 3.8](https://itheo.tech/install-python-38-on-a-raspberry-pi). Then, build aws-cli:
```bash
# Install Rust as a dependency
curl https://sh.rustup.rs -sSf | sh

git clone https://github.com/aws/aws-cli.git
cd aws-cli && git checkout v2
pip3.8 install -r requirements.txt
pip3.8 install .

aws --version
```

Configure AWS-CLI:
```bash
aws configure
```
Make sure to configure with the correct region name where
the KVSs are.

### [Run from Docker](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/examples-gstreamer-plugin.html#examples-gstreamer-plugin-docker)

**Create an IAM user on AWS with the KVS stream permissions and ECR access. Then, generate access credentials.**

The following are default policies that can be used:
```
AmazonKinesisVideoStreamsFullAccess
AWSAppRunnerServicePolicyForECRAccess
```

Authenticate to grab the docker image:
```bash
aws ecr get-login-password --region us-west-2 | docker login -u AWS --password-stdin https://546150905175.dkr.ecr.us-west-2.amazonaws.com
```

Pull the raspi docker image:
```bash
docker pull 546150905175.dkr.ecr.us-west-2.amazonaws.com/kinesis-video-producer-sdk-cpp-raspberry-pi:latest
```

Edit `rtsp_stream_kvs.sh` with the proper credentials and place
this file in `/opt/vc/`

Setup a `systemctl` service to automatically run it with
`rtsp-stream-kvs.service`. Edit the RTSP URL and stream name and place this
service file in `/etc/systemd/system/`.

Enable upon startup and start the service:
```bash
sudo systemctl enable rtsp-stream-kvs
sudo systemctl start rtsp-stream-kvs
```

Check the logs with
```bash
journalctl -u rtsp-stream-kvs -f
```

**Note:** If you get the error `Failed to load plugin... libmmal_core.so:...`, install 
`libraspberrypi0` and symlink it into the `/opt/vc/lib` directory:

```bash
sudo mkdir -p /opt/vc/lib
sudo ln -s /usr/lib/arm-linux-gnueabihf/libmmal_core.so.0 /opt/vc/lib/
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
