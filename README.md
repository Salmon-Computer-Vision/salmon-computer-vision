# Salmon Computer Vision Project

This repository contains several tools and utilities to assist in training
salmon counting automation tools. Two major categories include video-based
enumeration and sonar-based enumeration.

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
[Datumaro](https://github.com/openvinotoolkit/datumaro) to run.


### Training Steps

Navigate to the `utils` folder to use scripts to convert the data to MOT
sequences and YOLO format. Refer to the [this README](utils/README.md) for more
details.

## Sonar-based

Convert ARIS sonar files to videos with `pyARIS` using the Python 3 script
`./extract_aris/aris_to_video.py`.
