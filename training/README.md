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
