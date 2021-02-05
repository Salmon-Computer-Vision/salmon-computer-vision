# Utility Tools

```bash
./make_cvat_tasks.sh path/to/cvat/cli.py "user:${pass-env}" localhost path/to/labels.json path/to/annotations share_path
```

Creates tasks on CVAT instance and uploads/matches annotations to their respective videos on the share path.
