# Jetson-nano Setup

# Multi-Object Tracking only

Create a user named `salmonjetson` and make sure it has a homefolder `/home/salmonjetson`.

Login to that user.
```bash
sudo su salmonjetson
```

Place SSH deploy keys (`comp_vis_id_rsa`) for the computer-salmon-vision repo in `~/.ssh/`.

Run `./setup.sh`.

Create yolox model and ouputs directory:
```bash
mkdir -p ~/ByteTrack/YOLOX_outputs/yolox_nano_salmon
```

Put the converted model `model_trt.engine` in `yolox_nano_salmon`.

Pass the `bytetrack` docker image created for the Jetson Nano and load it on the Jetson.

Set static variables in `~/ByteTrack/docker-run.sh` such as the `prefix` and `fps`.

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

## SSH Reverse Tunnel

Create a new user solely for SSH tunnels/proxying.
```bash
sudo useradd tunnel
```

Create a group and add the new user:
```bash
sudo groupadd sshtunnel
sudo usermod -aG revtunnel tunnel
```

Login to tunnel user and generate a new SSH key with no passphrase:
```bash
sudo su tunnel
ssh-keygen -t rsa -b 4096 -f ~/.ssh/revtunnel_id_rsa
```

Add the `revtunnel_id_rsa.pub` public key to `~/.ssh/authorized_keys`.



# Old Setup with homesecurity

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
