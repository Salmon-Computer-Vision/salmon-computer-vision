# Raspberry Pi Services

The services outlined in `docker-compose.yml` will record continuous video
separated by 2 hours and perform motion detection, creating motion detected
clips at a maximum of 2 minutes.

There are currently one service that spin up their own docker container to perform tasks:

- `salmonmd-jetson` does the main work of motion detection and saving to the external harddrive

First, move to this folder:
```bash
cd utils/pi/services
```

Create your docker images using the respective dockerfiles in `Dockerfiles`:

```bash
docker build . -f Dockerfiles/Dockerfile-salmonmd-64 -t <image_repo_host>/salmonmd:<tag>
```

The `<image_repo_host>` is mainly for uploading to Docker Hub, but it'll be necessary for
the upcoming `.env` file.

If your raspberry pi is version 5 and 64-bit, use `Dockerfile-salmonmd-64`,
otherwise, use `Dockerfile-salmonmd` for older and 32-bit versions.

The environment file below will save video clips to this format:
```
# Motion detection
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/motion_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_M.mp4

# Continuous
${ORGID}/${SITE_NAME}/${DEVICE_ID_*}/cont_vids/${ORGID}-${SITE_NAME}-${DEVICE_ID_*}_<yyyymmdd>_<hhmmss>_C.mp4
```

Copy `template.env` to `.env` and populate the file.
```
cp template.env .env
```

Change the `jetson-0` in `DEVICE_ID` to the same name and number as ending
portion of the corresponding Jetson's hostname.

For example, if your raspi is `HMD-rivername-pi-1` and the corresponding jetson
is `HMD-rivername-jetson-1` put `jetson-1` here.

The `RTSP_URL` depends on what URL the camera streams out. For example, BARLUS cameras
have two main types:
```
RTSP_URL=rtsp://<ip.address>/av0_0
```
OR
```
RTSP_URL=rtsp://<ip.address>/0
```
Eg.
```
RTSP_URL=rtsp://192.168.1.120/0
```

Please check your camera's manual for the correct RTSP URL. Also, make sure the
cameras are set to static IPs.

Raspberry Pi 5 does not have a hardware encoder, so use the `--orin` flag to
use CPU encoding.

Change `DEVICE_ID` to the appropriate Jetson ending ID hostnames.

Ignore `BUCKET` if the device is deployed at a site with no Internet connectivity and as such
will not upload to the cloud. This param should be the AWS S3 bucket name to upload to.

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

To periodically sync logs to the external harddrive, copy the script to your local bin:
```bash
sudo cp sync_logs.sh /usr/local/bin/
sudo chmod +x /usr/local/bin/sync_logs.sh
```

You can change the `SRC_ROOT` and `DST_ROOT` folder as necessary.

Edit crontab:
```bash
sudo crontab -e
```

Add the following to the bottom:
```
0 */2 * * * /usr/local/bin/sync_logs.sh >> /var/log/sync_logs.log 2>&1
```

This will sync to the external harddrive every 2 hours.

Spin up docker containers and run them:
```bash
docker compose up -d
```

To restart, you can spin them down and then back up:
```bash
docker compose down && docker compose up -d
```

To run without cloud uploads, spin up only the `salmonmd-jetson` service:
```bash
docker compose up salmonmd-jetson -d
```

Check the logs to see if it is running and for troubleshooting:
```bash
docker compose logs --tail 10 -f
```

The other `syncing*` services deal with uploading to the cloud.

If you installed through pip, the command is simply `docker-compose` instead.

!! We have also discovered corruption errors that could occur when ingesting
the camera streams with older Raspberry Pis, so it may be beneficial to use
newer Raspberry Pis from the get-go.

### Healthchecks for HDD

Setup an extra healthchecks for the external harddrive mounting:

```bash
crontab -e
```

Put the following (Replace the URL with the correct ping address):

```
* * * * * df -h | grep media && curl -fsS -m 10 --retry 5 -o /dev/null https://hc-ping.com/<destination_address>
```

This assumes the external drive is mounted to `/media/hdd`.

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

Be careful as the `.env` file that will be read will be the current directory
of the ***HOST*** machine. This does however allow you to create all
environment files on the host machine without spreading them out to all of the
devices.

For example, you can have a `.env-raspi_example_river` to denote an environment
file for the Raspi at "Example River" on the host machine and then spin up its
docker containers remotely without needing to send this environment file:

```bash
docker --context remote compose --env-file .env-raspi_example_river up -d
```

The `--env-file` flag can be used more than once, so realistically, a common
`.env` file can also be created.

```bash
docker --context remote compose --env-file .env-common --env-file .env-raspi_example_river up -d
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
