# Jetson-nano Setup

## Setup Jetson Nano

Format SD card with SD card formatter with Quick format.

Flash SD card with Jetpack SDK using balenaEtcher.

To do headless mode, set the jumper to use the barrel power jack. Connect USB micro to Jetson Nano and
connect it to a computer. Connect an ethernet cable and then the power jack.

Follow instructions to install.

Run the following once you get to the terminal:

```bash
sudo apt update && sudo apt install apt-utils
sudo apt install ssh
```

Then, check if you can ssh into the Jetson:
```bash
ssh <username>@<hostname>.local
```

If success, you can safely exit the serial connection and unplug the micro USB.

## Multi-Object Tracking only

Create a user named `salmonjetson` if not already and make sure it has a homefolder `/home/salmonjetson`:
```bash
sudo useradd salmonjetson
ls /home
```

Login to that user.
```bash
sudo su salmonjetson
```

Pass over this entire folder:
```bash
scp -r jetson/ <username>@<hostname>.local:
```

SSH into the Jetson and run the setup:
```bash
cd jetson
./setup.sh
```

Reboot: `sudo reboot`

Create yolox model and ouputs directory:
```bash
mkdir -p ~/ByteTrack/YOLOX_outputs/yolox_nano_salmon
```

Put the converted model `model_trt.engine` in `yolox_nano_salmon`.

Pass the `bytetrack` docker image created for the Jetson Nano and load it on the Jetson.

Change the variables in `~/ByteTrack/docker-run.sh` such as the `prefix` and `fps` as needed.

Run the docker to test:
```bash
~/ByteTrack/docker-run.sh
```

Then, setup `systemctl` service with `multi-object-track.service`. Place this in `/etc/systemd/system/`
and edit the URL to point to the desired RTSP camera source.

Enable upon startup and start the service:
```bash
sudo systemctl enable multi-object-track
sudo systemctl start multi-object-track
```

Check the logs with
```bash
journalctl -u multi-object-track -f
```

## Old Setup with homesecurity

Clone jetson-inference and homesecurity.

Be sure to edit `common/config.py` for any required changes such as
changing the `mp4_folder` variable to point to a different destination.

`sudoedit /etc/docker/daemon.json` and add
```
"default-runtime": "nvidia"
```
within the curly braces.

For example your `/etc/docker/daemon.json` could look like this:

```
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    },
    "default-runtime": "nvidia"
}
```

Create docker image using the provided Dockerfile:
```
sudo docker build -t cam-detect -f Dockerfile-jetson-tf .
```

To convert YOLOv4 weights to TensorRT, copy the `*.weights` and `*.cfg` files
to the `homesecurity` folder, run the image, and run the following:

```
cp <yolov4-custom>.weights <yolov4-custom>.cfg /tensorrt_demos
cd /tensorrt_demos
python3 yolo_to_onnx.py -m <yolov4-custom>
python3 onnx_to_tensorrt.py -m <yolov4-custom>
```

Both `*.weights` and `*.cfg` must have the same name.

Then, copy `*.trt` to `homesecurity/yolo`, and `*.names` to the `homesecurity` folder.

## Running Image with Repo

```
cd ~/jetson-inference
docker/run.sh -c cam-detect -v /home/salmonjetson/homesecurity/:/homesecurity
```
