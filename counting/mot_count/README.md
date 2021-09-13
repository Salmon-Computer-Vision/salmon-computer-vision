# MOT Count

Currently, only a single class (fish) counting for videos or video streams.

First, move the `weights` folder provided to this directory.

Open up a command line window at this directory by going to the Windows
Explorer folder search bar and type in `cmd` and Enter.

Run the following command:

```
count.exe --input "<path\to\video-file>" --weights weights\latest.pt --cfg weights\cfg\yolo4.cfg
```

For example,
```
count.exe --input "10-30-2019 18-15-41 M Right Bank Underwater.m4v" --weights weights\latest.pt --cfg weights\cfg\yolo3.cfg
```

This will run the MOT detection and counting software for fish and output the
counts and video of the tracking bounding boxes in the `results` folder.
