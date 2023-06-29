# Salmon Computer Vision Project

This repository contains several tools and utilities to assist in training salmon counting automation tools. Two major categories include video-based enumeration and sonar-based enumeration.

## Video-based

Clone the annotations repository and download the video data (Pending availability):
```bash
git clone https://github.com/KamiCreed/salmon-count-labels.git
```

The current enumeration strategy is using two computer vision models: multi-object tracking (MOT) and object detection. We use [ByteTrack](https://github.com/Salmon-Computer-Vision/ByteTrack.git) for MOT and [YOLOv6](https://github.com/meituan/YOLOv6), respectively.

Navigate to the `utils` folder to use scripts to convert the data to MOT sequences and YOLO format. Refer to the [this README](utils/README.md) for more details.

## Sonar-based

Convert ARIS sonar files to videos with `pyARIS` using the Python 3 script `./extract_aris/aris_to_video.py`.
