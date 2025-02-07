# Salmon Counter

This will automatically count salmon by processing video clips in a specific
folder format, ignoring videos that have been created too early to prevent
attempting to process a currently recording video. The top level folder is
specified as an environment variable, however, the subfolders depend on the
hostname of the device.

The device running this docker container must have the following format:
```
${ORG}-${site}-jetson-#
```

For example,
```
HIRMD-tankeeah-jetson-0
```

Download the TensorRT `.engine` file weights and place it in the `config`
folder. Then, copy it to your home folder:

```bash
cp -r config ~/
```
OR the remote device's home folder:
```bash
scp -r config <user>@<host>:
```

Create an `.env` file here with the following:
```bash
IMAGE_REPO_HOST=<host>
TAG=<image_tag>
DRIVE=/media
USERNAME=<device-username>
WEIGHTS=/app/config/<salmoncount_weights>.engine

# Drop bounding boxes (optional flag)
# DROP_BOUNDING_BOXES: Set to "--drop-bbox" to remove top-view bounding boxes, or leave it empty to disable this option.
FLAGS=--drop-bbox
```

!! Make sure your drive folder is named `hdd` and is the next subdir after your `${DRIVE}` dir.
You must have the folder format in `${DRIVE}/hdd`.

If you have any private docker repos, you may need to install
the following to login with docker:
```bash
sudo apt install gnupg2 pass
```

Then, you should be able to login:
```bash
docker login
```

## [Temp] Build Jetpack 6 Ultralytics docker

This is for the Jetson Orin Nano as they use a newer Jetpack version.

Clone `ultralytics/ultralytics`

```bash
git clone --depth 1 https://github.com/ultralytics/ultralytics.git
```

Copy `Dockerfile-ultralytics-jetson-jetpack6` to the `docker` folder of where you cloned `ultralytics`.

Build the docker image on your Jetson Orin Nano with Jetpack 6:
```bash
cd ultralytics
docker build . -f docker/Dockerfile-ultralytics-jetson-jetpack6 -t <host>/ultralytics:latest-jetson-jetpack6
```

If you get a TLS block memory error, run the following beforehand:
```bash
export LD_PRELOAD=/usr/lib/aarch64-linux-gnu/libstdc++.so.6
```
