# Salmon Detection

Detects the species of the salmon and draws a bounding box with the confidence.

Command:

```
detectvideo.exe --weights checkpoints\yolov4-tiny-416 --tiny --size 416 --model yolov4 --video "<input-video-file>" --output <output-vid>.mp4 --dis_cv2_window
```

For example,
```
detectvideo.exe --weights checkpoints\yolov4-tiny-416 --tiny --size 416 --model yolov4 --video "09-25-2019 21-31-51 M Right Bank Underwater.mp4" --output det.mp4 --dis_cv2_window
```
