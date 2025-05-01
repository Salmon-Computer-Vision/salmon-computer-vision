# Salmon Computer Vision Model Training
## YOLOv8
Create YOLOv8 Jupyter Lab docker image as follows:
```bash
cd yolov8-notebook
docker build -t yolov8-dev .
cd ..
```

Then, you can run
```bash
./run-yolov8-docker.sh
```

Connect to the Jupyter Lab through `http://localhost:8888/lab` or through the URL with token specified
when the docker container is run.

Tuned hyperparameters are in `salmon_*_hyperparams.yaml`.

Copy the individual hyperparameters to `/usr/src/ultralytics/ultralytics/cfg/default.yaml` inside the
YOLOv8 docker container. Be careful to check each parameter, because you cannot directly copy them.

## Motion Detection

The bulk of the motion detection code is in `pysalmcount` module specifically
[`pysalmcount/pysalmcount/motion_detect_stream.py`](pysalmcount/pysalmcount/motion_detect_stream.py)

We run it through the script in
[`tools/run_motion_detect_rtsp.py`](tools/run_motion_detect_rtsp.py), however,
this requires installing the `pysalmcount` module which needs ultralytics/YOLO
to be installed on the computer, so if it is not done in a ultralytics docker
container, it could be best for an individual user to create their own running
script using the tool script as reference.

## Mounting Google Drive with rclone

Follow config for Google Drive
```bash
rclone config
```

Mount drive with cache to speed up operations:
```bash
rclone mount --vfs-cache-mode full --vfs-cache-max-size 100G "wiatlasdrive:Salmon Videos" Salmon_Videos
```
