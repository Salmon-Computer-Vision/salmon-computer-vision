# Object Detection

Training pipeline to train the SalmonVision object detection model.

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install DVC:
```bash
uv tool install dvc
```

Install the module:
```bash
uv pip install -e .
```

### Dataset

Setup `aws` cli on the machine to point to the remote storage described in `.dvc/config`.

Run the following to pull data:
```
dvc pull
```

All the data will be downloaded to `data`.

`data/04_dataset/salmon_dataset/dataset_sharded/` has the full dataset packed into tar shards.

You can manually perform tar extract or run the unpack step:
```bash
dvc repro --single-item --force unpack_split_dataset
```

This will unpack the tar files and put them in `data/04_dataset/salmon_dataset/yolo_workdir/`

### Pipeline

Check dvc.yaml for the full pipeline.

Run the following to run the entire pipeline:
```bash
dvc repro
```

Run the following to run specific stages of the pipeline:
```bash
dvc repro stage_name
```

This will still run previous stages up to the stage specified.

For example, building the model input annotations:
```bash
dvc repro build_model_input
```

If wanting to only run one stage, use the `--single-item` flag:
```bash
dvc repro --single-item build_model_input
```

Run tests with
```
uv run pytest
```
