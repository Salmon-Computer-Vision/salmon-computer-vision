# Salmon Computer Vision Project

This repository contains several tools and utilities to assist in training
salmon counting automation tools. Two major categories include [video-based](#video-based)
enumeration and [sonar-based](#sonar-based) enumeration.

## Video-based

The current enumeration strategy is using two computer vision models:
multi-object tracking (MOT) and object detection. We use
[ByteTrack](https://github.com/Salmon-Computer-Vision/ByteTrack.git) for MOT
and [YOLOv6](https://github.com/meituan/YOLOv6), respectively.

### Dataset

* Full dataset
  ([Dropbox](https://www.dropbox.com/sh/xv8i6k0hzo5jppn/AADBypR1zchux30gjUKGd4dLa?dl=0))
  of ~100 GB each for MOT and object detection.

It includes individual frame images and labels in the required format for
ByteTrack and YOLOv6. They could be easily converted to other similar formats
either manually or with
[Datumaro](https://github.com/openvinotoolkit/datumaro).

* Labels only ([GitHub
  repo](https://github.com/KamiCreed/salmon-count-labels.git)).

These annotations are in "CVAT for Video 1.1" format and include tags that
specify male/female, injuries, etc. It includes the Kitwanga River and Bear
Creek River bounding box annotations with no images. The conversion script is
in the `utils` folder (`utils/datum_create_dataset.py`), requiring
[Datumaro](https://github.com/openvinotoolkit/datumaro) to run. Refer to the
[this documentation](utils/README.md) for more details.


### Models

Trained on a Ubuntu 20.04 [Lambda
Scalar](https://lambdalabs.com/products/scalar) system with 4 A5000 GPUs.

#### Multi-Object Tracker (MOT)

The current framework uses ByteTrack to track individual salmon for counting.

The following steps are for Ubuntu 20.04:

Clone our version of the ByteTrack repo:
```bash
git clone https://github.com/Salmon-Computer-Vision/ByteTrack.git
cd ByteTrack
```

Follow either the docker install or host machine install in the [ByteTrack
documentation](https://github.com/Salmon-Computer-Vision/ByteTrack/blob/main/README.md)
to install all the requirements to run ByteTrack.

Download the `bytetrack_salmon.tar.gz` dataset from the [Dataset](#dataset)
section or convert the dataset to the MOT sequences format and use the script
in the `ByteTrack` repo to convert them to the COCO format.

Extract it and put the `salmon` folder in the `datasets` folder in `ByteTrack`
if not already.

```bash
tar xzvf bytetrack_salmon.tar.gz
```

Download the pretrained model YOLOX nano at their [model
zoo](https://github.com/Megvii-BaseDetection/YOLOX/tree/0.1.0).

Place the pretrained model in the `pretrained` folder. The path should be
`pretrained/yolox_nano.pth`.

Run the training either inside the docker container or on the host machine:
```bash
python3 tools/train.py -f exps/example/mot/yolox_nano_salmon.py -d 4 -b 256 --fp16 -o -c pretrained/yolox_nano.pth
```

If you canceled the training in the middle, you can resume from a checkpoint
with the following command:
```bash
python3 tools/train.py -f exps/example/mot/yolox_nano_salmon.py -d 4 -b 256 --fp16 -o --resume
```

Lower `-b` (batch size) if running on a GPU with less memory.

Once finished, the final outputs will be in `YOLOX_outputs/yolox_nano_salmon/`
where `best_ckpt.pth.tar` would be the checkpoint with the highest validation
mAP score.

To inference with the model on a video:

```bash
python3 tools/demo_track.py video -f exps/example/mot/yolox_nano_salmon.py -c pretrained/bytetrack_x_mot17.pth.tar --path path/to/video.mp4 --fp16 --fuse --save_result
```

Other options can be done with `demo_track.py` such as camera, and images. Run
the following to check them all:

```bash
python3 tools/demo_track.py -h
```

#### Object Detector

This will describe YOLOv6, however, the steps and format are similar for the other versions.

Clone the YOLOv6 repo:
```bash
git clone https://github.com/meituan/YOLOv6.git
```

Install Python3 requirements:
```bash
cd YOLOv6
pip3 install -r requirements.txt
```

Download the `yolov6_salmon.tar.gz` dataset from the [Dataset](#dataset)
section or convert the dataset to the YOLO format following the instructions in
the YOLOv6 repo.

Extract the dataset:
```bash
tar xzvf yolov6_salmon.tar.gz
```

Download the `combined_bear-kitwanga.yaml` file from the [Dataset](#dataset)
section and place it in the `data` folder which describes the location of the
dataset and the class labels. Please edit the yaml to point to where you
extract the dataset.

Run the training using multi-GPUs:

```bash
python -m torch.distributed.launch --nproc_per_node 4 tools/train.py --epoch 100 --batch 512 --conf configs/yolov6n_finetune.py --eval-interval 2 --data data/combined_bear-kitwanga.yaml --device 0,1,2,3
```

Lower `--batch` size appropriately if running on GPUs with less memory.

The final outputs will be in `runs/train/exp<X>`, where `<X>` is the number of
the run.

To run inferencing with YOLOv6:

```bash
python3 tools/infer.py \
    --yaml data/combined_bear-kitwanga.yaml \
    --weights runs/train/exp${X}/weights/best_ckpt.pt \
    --source "$vid" \
    --save-txt \
    --device $device
```

`$device` describes the number of the GPU device. If you only have one, `$device = 0`.

The resulting output will be in the `runs/inference` folder.

Check the YOLOv6 README for further inference commands or check `python3 tools/infer.py -h`.

## Sonar-based

Convert ARIS sonar files to videos with `pyARIS` using the Python 3 script
`./extract_aris/aris_to_video.py`.
