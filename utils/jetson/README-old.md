## Salmon Motion Detection

First setup NFS share from the Raspi to the Jetson to save videos to the external
drive attached to the Raspi.

### Running SalmonMD

Navigate to the `salmonmd` folder:
```bash
cd salmonmd
```

Create a `.env` file with the following:
```
IMAGE_REPO_HOST=<your_image_repo_host>
RTSP_URL=rtsp://<your_rtsp_url>
JETPACK_VER=<Jetpack version>
ORIN=<orin flag>
DRIVE=/media/hdd
FPS=10
```

FPS can be changed for your purposes, however, in previous tests,
the Jetson Nano can only process up to 12-14 FPS at 1920x1080 resolution
in real-time.

For example:
```
IMAGE_REPO_HOST=kamicreed
RTSP_URL=rtsp://192.168.1.191:554/av0_0
JETPACK_VER=r32.7.1
DRIVE=/media/hdd
FPS=10
```

For orin nano:
```
IMAGE_REPO_HOST=kamicreed
RTSP_URL=rtsp://192.168.1.191:554/av0_0
JETPACK_VER=r36.2.0
ORIN=--orin
DRIVE=/media/hdd
FPS=10
```

Valid values for `JETPACK_VER`: `r32.7.1`, `r36.2.0`

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

