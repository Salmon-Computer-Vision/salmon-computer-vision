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

Check dvc.yaml for the full pipeline.

Run the following to run specific stages of the pipeline:
```bash
dvc repro stage_name
```

For example, building the model input annotations:
```bash
dvc repro build_model_input
```
