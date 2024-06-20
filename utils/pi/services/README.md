Newer Raspberry Pi does not have any hardware encoder, 
so use the `--orin` flag to use CPU.

`.env` file:
```
IMAGE_REPO_HOST=<image_repo_host>
TAG=latest-bookworm
DRIVE=/media/hdd
USER=netlabmedia
ORGID=<orgid>
BUCKET=<bucket>
RTSP_URL_0=rtsp://<rtsp-url-0>
RTSP_URL_1=rtsp://<rtsp-url-1>
FPS=10
FLAGS=--orin
DEVICE_ID_0=--device-id jetson-0
DEVICE_ID_1=--device-id jetson-1
```

Older raspi do have the v4l2 or omx encoders:
```
IMAGE_REPO_HOST=<image_repo_host>
TAG=latest-buster
DRIVE=/media/hdd
USER=netlabmedia
ORGID=<orgid>
BUCKET=<bucket>
RTSP_URL_0=rtsp://<rtsp-url-0>
RTSP_URL_1=rtsp://<rtsp-url-1>
FPS=10
FLAGS=--raspi --gstreamer
DEVICE_ID_0=--device-id jetson-0
DEVICE_ID_1=--device-id jetson-1
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
