# Raspberry Pi utils

***This has been tested on Raspberry Pi 5 Bookworm.***

The Raspberry Pi will perform motion detection and record videos from RTSP
camera streams. It will also act as a network share using an external harddrive
and upload videos, detection files, and counts to the cloud.

If you have multiple devices that require setting up, you can perform this
setup once on one device and then clone the SD card for every other device to
save time.

! Remember to update the [hostname appropriately and restart Tailscale](../jetson/README.md#Rename-the-machine-Hostname).

## Install Docker and Docker compose

Follow the instructions to install docker on the raspberry pi:

https://docs.docker.com/engine/install/debian/

Add the raspi user to the docker group:
```bash
sudo usermod -aG docker <username>
```

Install Docker compose:
```bash
sudo apt update && sudo apt install docker-compose-plugin
```

If that does not exist, install through pip:
```bash
sudo apt install python3-pip
python3 -m pip install -U pip
python3 -m pip install -U docker-compose
```

## Tailscale

Tailscale is a remote connection software that can allow remote connections
past something like Starlink.

Follow the [Jetson instructions](../jetson/README.md#tailscale) in setting it up for the raspi.

## Auto-mounting external HDD

When a harddrive is plugged into the raspberry pi by default, it may be mounted
to a folder in `/media/{username}` using the name given by the drive. This can
be problematic for automation, so the following steps will automatically mount
the drive to a single location everytime a drive is plugged in. We use a
combination of udev rules and systemd to watch for a drive and execute a mount
when plugged in.

On the raspberry pi through SSH or in the terminal, clone this repo if you haven't already:
```bash
git clone --depth 1 https://github.com/Salmon-Computer-Vision/salmon-computer-vision.git
```

Go to the directory of this readme:
```bash
cd salmon-computer-vision/utils/pi
```

Create the mount folder:

```bash
sudo mkdir -p /media/hdd
```

Copy files in the `automount` folder to their respective places:
```bash
scripts_dir=automount
# Copy udev rules file
sudo cp ${scripts_dir}/99-external-hdd.rules /etc/udev/rules.d/
# Copy service file to system
sudo cp ${scripts_dir}/usb-mount@.service /etc/systemd/system/
# Copy script to root folder
sudo cp -p ${scripts_dir}/automount.sh /root/
sudo chmod +x /root/automount.sh
```

Then, reload the rules:
```bash
sudo udevadm control --reload-rules && sudo udevadm trigger
```

This will attempt to mount all partitions of a external drive to
a single folder, so this would only work if only one partition is
non-empty.

### Setup Samba Share

Having the external drive mounted is all good if we only need the one raspberry
pi to access the drive. However, we also need other devices or potentially
other raspis to accesss it to output or process videos and output the detection
and count files. We use Samba for compatibility of most drives out of the box.
Export a Samba share for the Jetson to access the external drive.

Install Samba:
```bash
sudo apt update && sudo apt install samba
```

Edit Samba config:
```bash
sudoedit /etc/samba/smb.conf
```

If you are using the old Jetson Nanos, they are only able to mount SMB ver 1.0
and lower shares (Set in the kernel), so place the following to allow SMB ver
1.0 under `[global]`:

```
[global]
workgroup = WORKGROUP
...
min protocol = NT1
```

Add the following at the end of the file:
```
[HDD]
path = /media/hdd
browseable = yes
read only = no
guest ok = yes
create mask = 0777
directory mask = 0777
inherit permissions = yes
force create mode = 0777
force directory mode = 0777
force user = <pi_username>
force group = <pi_username>
```

Restart Samba:
```bash
sudo systemctl restart smbd
```

## Set Static IP

To make sure the other devices can easily connect to the raspberry pi for
accessing the network share, set the raspberry pi with a static IP address.

Get the gateway and DNS IP addresses of the current network:
```bash
ip r # Can find gateway
grep "nameserver" /etc/resolv.conf # Get DNS IP address (Likely the gateway)
```

Depending on the Raspi, the network may be managed by dhcpcd or NetworkManager.

Check if dhcpcd is installed already:

```bash
apt list dhcpcd
```

If yes, jump to `dhcpcd`.

If not, use `nmcli` to setup the network:
```bash
sudo nmcli con add con-name eth0 ifname eth0 type ethernet autoconnect yes
sudo nmcli con mod eth0 ipv4.addresses 192.168.1.5/24
sudo nmcli con mod eth0 ipv4.gateway 192.168.1.1
sudo nmcli con mod eth0 ipv4.dns 192.168.1.1,1.1.1.1
sudo nmcli con mod eth0 ipv4.method manual
sudo nmcli con up eth0
```
Change `192.186.1.5` to your desired address.

### dhcpcd

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

## Software Services

Follow the instructions in the [`services` folder](services) to setup the docker images for running the
software.

## Setup for uploading to the cloud

We use `rclone` to facilitate the uploading, meaning once configured, the
uploading is agnostic to any cloud service provider as long as it's supported
by `rclone`. However, this has only been tested using AWS S3 buckets.

First install rclone:
```bash
sudo apt update && sudo apt install rclone
```

Go into the AWS console, and setup a user in AWS credentials that has access to
all or specific S3 buckets and generate their Access ID and Secret Key.

Follow the instructions after this command to configure rclone with AWS S3
buckets using that Access ID and Secret Key:

```bash
rclone config
```

!! Name the remote `aws`

Continue with instructions from the [README.md in the services folder](services/README.md).

## Streaming from RTSP to Amazon Kinesis Video Streams

Install dependecies:
```bash
sudo apt update && sudo apt install docker.io
```

Add user to docker group and log out and log back in:
```bash
sudo usermod -aG docker $USER
```

Check your RaspiOS architecture:
```bash
uname -m
```
If it shows `aarch64` continue on to 64-bit instructions if not, skip to 32-bit.

### [In-progress] RaspiOS 64-bit
Download the installer:
```bash
curl -O 'https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip'
```

Unzip and install:
```bash
unzip awscli-exe-linux-aarch64.zip
sudo ./aws/install
```

Check if it works:
```bash
aws --version
```

### RaspiOS 32-bit
For raspi 32-bit, AWS-CLIv2 is not officially supported,
so we will build it using Python. [First install Python 3.8](https://itheo.tech/install-python-38-on-a-raspberry-pi).

```bash
sudo apt update && sudo apt install cmake
```

Then, build aws-cli:
```bash
# Install Rust as a dependency
curl https://sh.rustup.rs -sSf | sh

git clone https://github.com/aws/aws-cli.git
cd aws-cli && git checkout v2
pip3.8 install -r requirements.txt
pip3.8 install .

aws --version
```

### [Run from Docker](https://docs.aws.amazon.com/kinesisvideostreams/latest/dg/examples-gstreamer-plugin.html#examples-gstreamer-plugin-docker)

**Create an IAM user on AWS with the KVS stream permissions and ECR access. Then, generate access credentials.**

The following are default policies that can be used:
```
AmazonKinesisVideoStreamsFullAccess
AWSAppRunnerServicePolicyForECRAccess
```

Go to the AWS console and setup streams for each camera that will be streamed to it
in the Kinesis Video Streams (KVS) dashboard. The name does not matter but it will
be used as the key to target the stream. A good naming structure could be `ORGID-rivername-stream-0`.

On the raspi setup the access credentials:
```bash
aws configure
```
Make sure to configure with the correct region name where
the KVSs are.

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
