Newer Raspberry Pi does not have any hardware encoder, 
so use the `--orin` flag to use CPU.

`.env` file:
```
HOST=<image_repo_host>
DRIVE=/media/hdd
USER=netlabmedia
ORGID=<orgid>
BUCKET=<bucket>
RTSP_URL_0=rtsp://<rtsp-url-0>
RTSP_URL_1=rtsp://<rtsp-url-1>
FPS=10
ORIN=--orin
DEVICE_ID_0=--device-id jetson-0
DEVICE_ID_1=--device-id jetson-1
```
