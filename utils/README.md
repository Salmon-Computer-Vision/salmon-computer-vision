# Utility Tools

If there are new labels, first, manually convert the XML \<labels\> in the `annotation.xml` file to JSON. Copy
it to `labels.json` Then, run

```bash
./jq-labels.sh labels.json > labels-converted.json
```

This creates the labels required to create CVAT tasks.

```bash
./make_cvat_tasks.sh path/to/cvat/cli.py "user:${pass-env}" localhost path/to/labels.json path/to/annotations share_path
```

Creates tasks on CVAT instance and uploads/matches annotations to their respective videos on the share path.

```bash
./dump_cvat.sh path/to/cvat/cli.py "user:${pass-env}" localhost <start-task-id> <last-task-id> dest/dir
./merge_datum.sh user "${pass-env}" source/dump/annotations filter/dir dest/dir
./convert_tf.sh source/datumaro dest/dir
```

### datum\_create\_dataset.py
Exports dataset based on CSV file:
```bash
./datum_create_dataset.py -j 4 --anno-path annos --proj-path datum_proj --transform-path datum_proj_transform --mot-path export_mot /mnt/disk5tb/salmon_anno_bear_creek_123.csv
```

The CSV file must be of format:
```
filename,vid_path,anno_path
07-15-2020 15-51-08 M Left Bank Underwater,/path/to/vids/07-15-2020 15-51-08 M Left Bank Underwater.m4v,/path/to/annos/07-15-2020_15-51-08_M_Left_Bank_Underwater.zip
...
```
