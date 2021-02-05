# Utility Tools

```bash
./make_cvat_tasks.sh path/to/cvat/cli.py "user:${pass-env}" localhost path/to/labels.json path/to/annotations share_path
```

Creates tasks on CVAT instance and uploads/matches annotations to their respective videos on the share path.

```bash
./dump_cvat.sh path/to/cvat/cli.py "user:${pass-env}" localhost <start-task-id> <last-task-id> dest/dir
./merge_datum.sh user "${pass-env}" source/dump/annotations filter/dir dest/dir
./convert_tf.sh source/datumaro dest/dir
```
