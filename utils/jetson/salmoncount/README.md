# Salmon Counter

The Salmon Counter runs the deep learning model to automatically detect fish
species, track their position, and count each species. This is done by
processing video clips in a specific folder format, ignoring videos that have
been created too early to prevent processing a currently recording video. The
top level folder is specified as an `.env` variable, however, ***the subfolders
depend on the hostname*** of the device.

First, go to this directory:
```bash
cd utils/jetson/salmoncount
```

Build the salmoncounter docker image:
```bash
docker build -t <host>/salmoncounter:latest-jetson-jetpack4 .
```

The device running this docker container ***must*** have the following format:
```
${ORG}-${site}-jetson-#
```

For example,
```
HIRMD-tankeeah-jetson-0
```

Download the [TensorRT `.engine` file weights](/README.md#dataset-and-models)
and place it in the `config` folder. Then, copy it to the device's home folder:

```bash
cp -r config ~/
```

Create an `.env` file here with the following:
```bash
IMAGE_REPO_HOST=<host>
TAG=latest-jetson-jetpack4
DRIVE=/media
USERNAME=<device-username>
WEIGHTS=/app/config/<salmoncount_weights>.engine

# FLAGS

# Drop bounding boxes (optional): Uncomment and set "--drop-bbox" to remove
# top-view bounding boxes on the bottom half of each frame for cameras with a
# mirror displaying both top and side view

#FLAGS=--drop-bbox
```

!! Make sure your drive folder is named `hdd` and is the next subdir after your `${DRIVE}` dir.
You must have the folder format in `${DRIVE}/hdd`.

The folders in `WEIGHTS` describe within the docker container, so simply
make sure the `<salmoncount_weights>.engine` name is the same in the config
folder.

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
