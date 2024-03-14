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
flags to turn it to only a single thread/process. This can be done
after running once in parallel to catch only the ones that had errors. 

## Examples

By default, process CVAT annotations converting `__instance_id` to `track_id` and outputting as Datumaro, filtering items with annotations.
```bash
cd output_symlink
python3 ../process_cvat_xml.py --save-media ../../DDD_annos/DDD\ UPLOAD/ /mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2024-03-01/ ../../2023_combined_salmon.yaml
```

Update old datumaro annotations to conform to new labels:
```bash
python3 ./process_cvat_xml.py --no-filter -f datumaro --save-media ~/salmon-computer-vision/utils/datum_proj_kitwanga/ /mnt/ayumissd4tb/masamim/salm_dataset_kitwanga_2019-2020/ ../2023_combined_salmon.yaml
```

Convert to YOLO format while filtering to a specified test set.
```bash
python3 ./process_cvat_xml.py --no-filter -f datumaro -o yolo --save-media --set-file ../train_splits/test_koeye_2023.csv /mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2024-03-01/ /mnt/ayumissd4tb/masamim/salm_dataset_yolo_koeye_2023/test ../2023_combined_salmon.yaml
```

Output 5 random empty frames from each sequence for the test set.
```bash
python3 ../process_cvat_xml.py --workers 1 --no-filter -o yolo --save-media --empty-only --num-empty 5 --set-file ../../train_splits/test_koeye_2023.csv --anno-name output.xml ../../DDD_annos/DDD\ UPLOAD /mnt/ayumissd4tb/masamim/salm_dataset_yolo_empty_koeye_2023/test ../../2023_combined_salmon.yaml
```
