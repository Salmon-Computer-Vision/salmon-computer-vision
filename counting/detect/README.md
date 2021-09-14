# Salmon Detection

Detects the species of the salmon and draws a bounding box with the confidence.

First, move the `checkpoints` folder provided to `detectvideos` directory.

Open up a command line window at the `detectvideos` directory by going to the
Windows Explorer folder search bar and type in `cmd` and Enter.

Run the following command:

```
detectvideo.exe --weights checkpoints\yolov4-tiny-416 --tiny --size 416 --model yolov4 --video "<input-video-file>" --output <output-vid>.mp4 --dis_cv2_window
```

For example,
```
detectvideo.exe --weights checkpoints\yolov4-tiny-416 --tiny --size 416 --model yolov4 --video "09-24-2019 17-10-19 M Right Bank Underwater.mp4" --output det.mp4 --dis_cv2_window
```

This would run the salmon detection on the provided video and output another
video named `det.mp4` (In this example) with drawn bounding boxes and labeled
species to the specified file.

You can remove `--dis_cv2_window` to see the detection while it is running.
