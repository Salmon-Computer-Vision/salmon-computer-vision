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

Run the docker.
```bash
~/ByeteTrack/docker-run.sh
```

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
