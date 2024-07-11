Create your docker images using the respective dockerfiles in `Dockerfiles`:
```bash
docker build . -f Dockerfiles/Dockerfile-salmonmd -t <host>/salmonmd:<tag>
```

Create a `.env` file with the following:

Newer Raspberry Pi does not have any hardware encoder, 
so use the `--orin` flag to use CPU.

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
