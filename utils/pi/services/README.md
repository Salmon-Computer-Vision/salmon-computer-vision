Create your docker images using the respective dockerfiles in `Dockerfiles`:
```bash
docker build . -f Dockerfiles/Dockerfile-salmonmd -t <host>/salmonmd:<tag>
```

Create a `.env` file with the following:

Newer Raspberry Pi does not have any hardware encoder, 
so use the `--orin` flag to use CPU.

The environment file below will save video clips to this format:
```
# Motion detected
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/motion_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_M.mp4

# Continuous
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/cont_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_C.mp4
```

`.env` file:
```
IMAGE_REPO_HOST=<image_repo_host>
TAG=latest-bookworm
DRIVE=/media/hdd
USERNAME=netlabmedia
ORGID=<orgid>
SITE_NAME=<site_name>
BUCKET=<bucket>
RTSP_URL_0=rtsp://<rtsp-url-0>
RTSP_URL_1=rtsp://<rtsp-url-1>
FPS=10
FLAGS=--orin --algo CNT
DEVICE_ID_0=--device-id jetson-0
DEVICE_ID_1=--device-id jetson-1
```

Older raspi do have the v4l2 or omx encoders:
```
...
TAG=latest-buster
...
FLAGS=--raspi --gstreamer --algo CNT
...
```

Sometimes the RTSP stream fails to open with gstreamer. If so,
turn off gstreamer decoding by removing the `--gstreamer` flag.

### Remote Docker Commands

Docker contexts are one of the keys to run docker commands over ssh.

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
