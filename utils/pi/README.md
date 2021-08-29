# Raspberry Pi utils

The service file and cam.sh script runs FFMPEG to record the RTSP
videos from the IP Cameras that are deployed.

## Raspberry Pi DHCP

To run a DHCP server on the Raspberry Pi use this package:

```
sudo apt install isc-dhcp-server
```

This installs a service that acts as the server. Check the status as such:
```
sudo systemctl status isc-dhcp-server.service
```
