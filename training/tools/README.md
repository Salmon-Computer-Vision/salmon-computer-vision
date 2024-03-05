# tools

First get environment:

```bash
pipenv shell
```

Then, can run the following scripts *in this order*:
```bash
extract_frames.py

process_cvat_xml.py
```

If the disk doesn't have enough space to extract all of the frames
including empty frames, `process_cvat_xml.py` automatically removes
empty frames and outputs an `error*.txt` file showing all of the
filepaths that were not processed correctly. This can be fed into
`extract_frames.py` to filter the video paths.
