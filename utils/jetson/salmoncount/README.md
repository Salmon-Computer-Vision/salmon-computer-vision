# Salmon Counter

Place TensorRT engine file weights in the `config` folder and then copy it to your home folder:
```bash
cp -r config ~/
```
Or the remote device's home folder:
```bash
scp -r config <user>@<host>:
```

Create an `.env` file here with the following:
```
IMAGE_REPO_HOST=<host>
TAG=<image_tag>
DRIVE=/media
USERNAME=<device-username>
HOST_UID=1000
HOST_GID=1000
WEIGHTS=/app/config/<salmoncount_weights>.engine
```

!! Make sure your drive folder is named `hdd` and is the next subdir after your `${DRIVE}` dir.

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
