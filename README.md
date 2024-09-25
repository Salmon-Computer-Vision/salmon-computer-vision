# Salmon Computer Vision Project

This repository contains several tools and utilities to assist in training
salmon counting automation tools as well as to deploy to edge devices for
edge-based processing of videos. Two major categories include
[video-based](#video-based) enumeration and [sonar-based](#sonar-based)
enumeration.

## License

The code is currently under the [MIT License](LICENSE) but could be subject to change in the future.

The data and annotation are under [Creative Commons BY-NC-SA 4.0](LICENSE-Data) ([Official
license](https://creativecommons.org/licenses/by-nc-sa/4.0/)).
No commercial usage and any adaptations must be published with the same license.

Any Salmon Vision models published here is under the [ResearchRAIL license](LICENSE-Model.md) for research purposes only.

## Video-based

The current enumeration strategy is using two computer vision models:
multi-object tracking (MOT) and object detection. We use
[ByteTrack](https://github.com/Salmon-Computer-Vision/ByteTrack.git) for MOT
and [YOLOv6](https://github.com/meituan/YOLOv6), respectively.

### Dataset

* Full dataset and model
  ([Dropbox](https://www.dropbox.com/sh/xv8i6k0hzo5jppn/AADBypR1zchux30gjUKGd4dLa?dl=0))
  of ~100 GB each for MOT and object detection.

It includes individual frame images and labels in the required format for
ByteTrack and YOLOv6. They could be easily converted to other similar formats
either manually or with
[Datumaro](https://github.com/openvinotoolkit/datumaro). The pre-trained models are
also there with a preliminary YOLOv8 model.

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

The current strategy is to use YOLOv8's suite of tools to perform both
object detection of salmon species and multi-object tracking of salmon
throughout multiple frames.

Look into the [`training` folder](training/README.md)
for more info about training the model.

### Edge Deployment

To deploy our automated salmon counting system on the edge near rivers for near
real-time processing, we use two main types of microprocessors: Raspberry Pis
and Jetson Nanos.

[The Raspberry Pi setup instructions are here](utils/pi/README.md).

[Jetsons Nano setup instructions are here](utils/jetson/README.md).

The bash script `deploy-system.sh` can be used to automatically deploy the services
to all of your remote devices. Simply create and fill in a `deploy-vars.sh` file in
the `utils` directory with the following:

```bash
#!/usr/bin/env bash
# utils/deploy-vars.sh
MAX_DEVICES=2

sites=(
    hirmd-koeye
    # Other sites here...
)

# Define an array of systems, each with its own image and environment file
declare -A systems=(
    ["jetsonorin"]="<host>/salmoncounter:latest-jetson-jetpack6"
    ["jetson"]="<host>/salmoncounter:latest-jetson-jetpack4"
    ["pi"]="<host>/salmonmd:latest-bookworm"
)
```

Run the script as such
```bash
cd utils
./deploy-system.sh
```

## Sonar-based

Convert ARIS sonar files to videos with `pyARIS` using the Python 3 script
`./extract_aris/aris_to_video.py`.
