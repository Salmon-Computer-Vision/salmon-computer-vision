# Jetson-nano Setup

> ⚠️ A Jetson already setup previously may be difficult to access due to [static IP address](#setup-static-ip) 
used to make sure the IP does not change when connected to the Starlink router. Either change your computer
IP address to the same gateway, look into [serial connection with a micro-USB](https://developer.nvidia.com/embedded/learn/get-started-jetson-nano-2gb-devkit#setup-headless),
or connect with an HDMI cable.

## Tailscale

Tailscale is a remote connection software. Copy `docker-compose-template.yaml` to `docker-compose.yaml` and update with the auth key from Tailscale.

On the Jetson Nano, install docker-compose:
```
python3 -m pip install -U pip
python3 -m pip install docker-compose
```

Run the following in this directory to start up Tailscale:
```
docker-compose up -d
```

The shut it down do
```
docker-compose down
```

### Rename the machine Hostname

Update the hostname of the device if not already to change the name on the admin console:
```
sudo hostnamectl set-hostname <new-hostname>
```
If this is run after Tailscale is already up, reboot the machine and do the following:

First, delete the Tailscale status folder (the folder name can be different depending on the YAML file)
```
sudo rm tailscale-oauth/ -r
```
***!!!*** Then, you ***MUST*** run the following command under the ***Tmux environment***, otherwise, you are likely to lose the SSH remote connection permanently.
```
docker-compose down && docker-compose up -d
```

### Update the Docker Tailscale
```
docker pull tailscale/tailscale:latest
```
Then restart the docker-compose as above in the Tmux environment. 

We will standardize the hostnames as such
```
<ORG-ID>-<river-name>-<device>-<num>
```
`<device>` could be `pi` or `jetson`.

For example,
```
KXSA-kwakwa-jetson-0
```

## Salmon Motion Detection

First setup NFS share from the Raspi to the Jetson to save videos to the external
drive attached to the Raspi.

### Samba Share

To mount the NFS share and recover automatically from the raspi install NFS client and autofs:
```bash
sudo apt update && sudo apt install cifs-utils autofs
```

Create mount dir:
```bash
sudo mkdir -p /media/hdd
```

Edit `/etc/auto.master`:
```bash
sudoedit /etc/auto.master
```

Add the following to the bottom:
```bash
/- /etc/auto_static.smb --timeout=60
```

Create a new file:
```bash
sudoedit /etc/auto_static.smb
```

with the following:
```bash
/media/hdd  -fstype=cifs,rw,guest,uid=1000,file_mode=0777,dir_mode=0777  ://<raspi_ip>/HDD
```
Replace `<raspi_ip>` with the static IP address of the Raspberry Pi that is mounting
the external drive.

Restart the autofs service:
```bash
sudo systemctl restart autofs
```

### Running SalmonMD

Navigate to the `salmonmd` folder:
```bash
cd salmonmd
```

Create a `.env` file with the following:
```
IMAGE_REPO_HOST=<your_image_repo_host>
RTSP_URL=rtsp://<your_rtsp_url>
DRIVE=/media/hdd
FPS=10
```

FPS can be changed for your purposes, however, in previous tests,
the Jetson Nano can only process up to 12-14 FPS at 1920x1080 resolution
in real-time.

For example:
```
IMAGE_REPO_HOST=kamicreed
RTSP_URL=rtsp://192.168.1.191/av0_0
```

If you are using a local docker registry, add your hostname to `/etc/docker/daemon.json`:
```
{ 
    "insecure-registries": ["your_hostname.local:5000"] 
}
```

Run docker-compose in the `salmonmd` folder:
```bash
docker-compose up -d
```

## ultralytics docker setup

Try pulling and running ultralytics from main docker first:
```
t=ultralytics/ultralytics:latest-jetson && sudo docker pull $t && sudo docker run -it --ipc=host --runtime=nvidia $t
```

Otherwise, follow [ultralytics steps](https://github.com/ultralytics/ultralytics.git) to build your own docker image for Jetson:


## Setup Jetson Nano

Format SD card with SD card formatter with Quick format.

Flash SD card with Jetpack SDK using balenaEtcher.

To do headless mode, set the jumper to use the barrel power jack or USB-C (2GB only). Connect USB micro to Jetson Nano and
connect it to a computer. Connect an ethernet cable and then the power jack.

> ⚠️ Connecting using a barrel power jack or USB-C is required anyways to use Jetson Nano at MaxN (10W) or maximum performance mode. Be sure to get
a barrel jack with at least 10W of output.

Follow instructions to install.

Run the following once you get to the terminal:

```bash
sudo apt update && sudo apt install apt-utils
sudo apt install ssh
```

Then, check if you can ssh into the Jetson:
```bash
ssh <username>@<hostname>.local
```

If success, you can safely exit the serial connection and unplug the micro USB.

## Multi-Object Tracking only

Create a user named `salmonjetson` if not already and make sure it has a homefolder `/home/salmonjetson`:
```bash
sudo useradd salmonjetson
ls /home
```

Login to that user.
```bash
sudo su salmonjetson
```

Pass over this entire folder:
```bash
scp -r jetson/ <username>@<hostname>.local:
```

SSH into the Jetson and run the setup:
```bash
cd jetson
sudo ./setup.sh
```

Reboot: `sudo reboot`

Put the converted model `model_trt.engine` in `yolox_nano_salmon`:
```bash
scp model_trt.engine salmonjetson@<jetson_hostname>:/home/salmonjetson/ByteTrack/YOLOX_outputs/yolox_nano_salmon
```

Pass the `bytetrack` docker image created for the Jetson Nano and load it on the Jetson.
```bash
sudo apt install pv # Install progress monitor if not already
# Un-compressed network transfer - recommended if LAN
cat bytetrack_manual.tar | pv | ssh salmonjetson@<jetson_hostname> docker load
```

OR
```bash
# Compressed network transfer - works only if CPU of target machine is powerful
# On Jetson Nano, this is only ~2 MB/s for a compressed 2 GB file
cat bytetrack_manual.tar.bz2 | pv | ssh salmonjetson@<jetson_hostname> docker load
```
OR 

Even better, setup a [local registry](https://www.allisonthackston.com/articles/local-docker-registry.html).

Run the registry docker on the docker image host machine:
```bash
docker run -d -p 5000:5000 --restart always --name registry registry:2
```

Using the hostname and port of that host machine, edit `/etc/docker/daemon.json` by adding the following:
```
{
    "insecure-registries": ["your_hostname.local:5000"]
}
```

Then, push and pull using this hostname prepended to the docker image tag:
```
docker tag your_docker_image your_hostname.local:5000/your_docker_image
docker push your_hostname.local:5000/your_docker_image
```

```
docker pull your_hostname.local:5000/your_docker_image
```

For saving to a shared harddrive, set an sshfs from the outputs folder to the external hard disk on the raspi:

```bash
mkdir ~/ByteTrack/YOLOX_outputs/track_outputs/
sshfs lockedsaphen@raspberrypi.local:/media/usb0/ ~/ByteTrack/YOLOX_outputs/track_outputs/ -o IdentityFile=~/.ssh/revtunnel_id_rsa
```

Change the variables in `~/ByteTrack/docker-run.sh` such as the `prefix` and `fps` as needed.

Test the docker to see if it is working:
```bash
~/ByteTrack/docker-run.sh bytetrack rtsp://<url>
```

The output of the videos and CSV tracks go in the `YOLOX_outputs` folder. You can symlink this
folder to an external harddrive if needed.

If it works, setup a `systemctl` service to automatically run this with
`multi-object-track.service`. Place this service file in `/etc/systemd/system/`
and edit the URL to point to the desired RTSP camera source.

Enable upon startup and start the service:
```bash
sudo systemctl enable multi-object-track
sudo systemctl start multi-object-track
```

Check the logs with
```bash
journalctl -u multi-object-track -f
```

## Setup Static IP

Jetson Nano by default uses Network Manager to provision its networking.

Use `nm-connection-editor` or the CLI to edit the IPv4 static IP.

```bash
sudo nm-connection-editor
```

By default Starlink uses the following:
* Gateway: 192.168.1.1
* DNS: 192.168.1.1
* Netmask: 255.255.255.0 OR 24

Here are the series of commands with `nmcli`:
```bash
sudo nmcli con add con-name eth0 ifname eth0 type ethernet autoconnect yes
sudo nmcli con mod eth0 ipv4.addresses 192.168.1.20/24
sudo nmcli con mod eth0 ipv4.gateway 192.168.1.1
sudo nmcli con mod eth0 ipv4.dns 192.168.1.1,1.1.1.1
sudo nmcli con mod eth0 ipv4.method manual
sudo nmcli con up eth0
```
Replace `192.168.1.20` with your perferred address.
Check `nmcli con show` to find the correct network interface if it's not `eth0`.

## Barlus Camera Caveats

PTZ usage works by inputting the numeric value in the box and pressing the "Call" button to incur the
described function.

For example, set the value as 250 and click "Call" to save the lighting configuration.

## Old Setup with homesecurity

Clone jetson-inference and homesecurity.

Be sure to edit `common/config.py` for any required changes such as
changing the `mp4_folder` variable to point to a different destination.

`sudoedit /etc/docker/daemon.json` and add
```
"default-runtime": "nvidia"
```
within the curly braces.

For example your `/etc/docker/daemon.json` could look like this:

```
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
```

Create docker image using the provided Dockerfile:
```
sudo docker build -t cam-detect -f Dockerfile-jetson-tf .
```

To convert YOLOv4 weights to TensorRT, copy the `*.weights` and `*.cfg` files
to the `homesecurity` folder, run the image, and run the following:

```
cp <yolov4-custom>.weights <yolov4-custom>.cfg /tensorrt_demos
cd /tensorrt_demos
python3 yolo_to_onnx.py -m <yolov4-custom>
python3 onnx_to_tensorrt.py -m <yolov4-custom>
```

Both `*.weights` and `*.cfg` must have the same name.

Then, copy `*.trt` to `homesecurity/yolo`, and `*.names` to the `homesecurity` folder.

## Running Image with Repo

```
cd ~/jetson-inference
docker/run.sh -c cam-detect -v /home/salmonjetson/homesecurity/:/homesecurity
```
