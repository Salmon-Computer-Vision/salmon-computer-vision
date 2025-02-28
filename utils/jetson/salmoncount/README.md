# Salmon Counter

The Salmon Counter runs the deep learning model to automatically detect fish
species, track their position, and count each species. This is done by
processing video clips in a specific folder format, ignoring videos that have
been created too early to prevent processing a currently recording video. The
top level folder is specified as an `.env` variable, however, ***the subfolders
depend on the hostname*** of the device.

First, go to this directory:
```bash
cd salmon-computer-vision/utils/jetson/salmoncount
```

Build the salmoncounter docker image:
```bash
docker build -t <image_repo_host>/salmoncounter:latest-jetson-jetpack4 .
```

`<image_repo_host>` here refers to the image repository host that you may
upload this built docker image to if you so choose. [See the updating docker
image section](#uploading-the-docker-image) for more info.

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

Create an `.env` file in the `salmoncount` with the following:
```bash
IMAGE_REPO_HOST=<image_repo_host>
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

Spin up the services:
```bash
docker compose up -d
```

To restart, you can spin them down and then back up:
```bash
docker compose down && docker compose up -d
```

Check the logs to see if it is running and for troubleshooting:
```bash
docker compose logs --tail 10 -f
```

## Uploading the Docker Image

Uploading the docker image could make updating or pulling the image to other
devices more streamlined instead of having to build the image for each device.
This could be something as simple as a public Docker Hub repo.

If you have made changes to the code, you can update the docker image by
rebuilding as shown above ideally on a dev device (Maybe with `--no-cache` if
needed). The following outlines the steps on uploading the docker images.

Login to your image repo:

```bash
docker login
```

If you have any private docker repos, you may need to install
the following to login with docker:
```bash
sudo apt install gnupg2 pass
```

Then, you should be able to login:
```bash
docker login
```

Push your docker image:

```bash
docker push <image_repo_host>/salmoncounter:latest-jetson-jetpack4
```

Make sure `<image_repo_host>` is either your Docker Hub account username or the
URL of your private docker image repository.

Once it is pushed, it will live in the cloud of whatever repository you pushed
to. Then, you can go to your other devices and pull the image and any changes.

On the production devices, run the following to update:

```bash
docker pull <image_repo_host>/salmoncounter:latest-jetson-jetpack4
```

Spinning the services up again should automatically update the container:

```bash
docker compose up -d
```

Otherwise, you can fully remove and spin them back up:

```bash
docker compose down && docker compose up -d
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
