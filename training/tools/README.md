# tools

First get environment:

```bash
pipenv shell
```

Then, can run the following scripts *in this order*:
```bash
extract_frames.py

cd output_symlink
../process_cvat_xml.py
```

If the disk doesn't have enough space to extract all of the frames
including empty frames, `process_cvat_xml.py` automatically removes
empty frames and outputs an `error*.txt` file showing all of the
filepaths that were not processed correctly. This can be fed into
`extract_frames.py` to filter the video paths.

If the filtered annotation comes out empty, the resulting Datumaro
conversion will not output any annotation file.

`process_cvat_xml.py` may fail if one of the XML files are large
and takes a long time to process as this can cause errors processing
the other data in parallel. One fix is to set `--workers 1` in the
flags to turn it to only a single thread/process.
