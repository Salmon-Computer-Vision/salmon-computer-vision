# Raspberry Pi Services

These services outlined in `docker-compose.yml` will perform motion detection,
and uploading to the cloud. For a Raspberry Pi 5, the potential maximum is two
simultaneous streams, and even then that may be too much considering all of the
other tasks the Raspberry Pi needs to do.

Create your docker images using the respective dockerfiles in `Dockerfiles`:

```bash
docker build . -f Dockerfiles/Dockerfile-salmonmd-64 -t <host>/salmonmd:<tag>
```

If your raspberry pi is version 5 and 64-bit, use `Dockerfile-salmonmd-64`,
otherwise, use `Dockerfile-salmonmd` for older and 32-bit versions.

The environment file below will save video clips to this format:
```
# Motion detection
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/motion_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_M.mp4

# Continuous
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/cont_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_C.mp4
```

Create a `.env` file here with the following:
```
IMAGE_REPO_HOST=<image_repo_host>
TAG=latest-bookworm
DRIVE=/media/hdd
USERNAME=netlabmedia
HOST_UID=1000
HOST_GID=1000
ORGID=<orgid>
SITE_NAME=<site_name>
BUCKET=<bucket>
RTSP_URL=rtsp://<rtsp-url>
FPS=10
FLAGS=--orin --algo CNT
DEVICE_ID=--device-id jetson-0
```

Raspberry Pi 5 does not have a hardware encoder, so use the `--orin` flag to
use CPU encoding.

Change the `RTSP_URL` and `DEVICE_ID` to the respective URLs and Jetson ending ID hostnames.


Older raspi do have the v4l2 or omx encoders, so set the vars like this
instead:

```
...
TAG=latest-buster
...
FLAGS=--raspi --gstreamer --algo CNT
...
```

Sometimes the RTSP stream fails to open with gstreamer. If so, turn off
gstreamer decoding by removing the `--gstreamer` flag.

Spin up docker containers and run them:
```bash
docker compose up -d
```

To restart, you can spin them down and then back up:
```bash
docker compose down && docker compose up -d
```

If you installed through pip, the command is simply `docker-compose` instead.

!! We have also discovered corruption errors that could occur with older
Raspberry Pis, so it may be beneficial to use newer Raspberry Pis from the
get-go.

### Remote Docker Commands

Docker contexts are very convenient to run docker commands over ssh.

For example,

```bash
docker context create remote --docker "host=ssh://netlabmedia@192.168.1.5"
```

This will create a context that will send docker commands over ssh to the host specified.

List all contexts:
```bash
docker context ls
```

Run command on different context:
```bash
docker --context remote ps
```

Switch to context
```bash
docker context use remote
docker ps
```

### Increase swap memory

This is likely not necessary for newer raspberry pis but can be helpful if the
raspberry pi does not have enough memory for all these services.

Stop using swap:
```bash
sudo dphys-swapfile swapoff
```

Edit config:
```bash
sudoedit /etc/dphys-swapfile
```

Find the following:
```
CONF_SWAPSIZE=100
```

Replace with desired size, eg. 2GB:
```
CONF_SWAPSIZE=2048
```

Setup and put the swap back on:
```
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

Then, reboot:
```
sudo reboot
```
