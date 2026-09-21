# Object Detection

Training pipeline to train the SalmonVision object detection model.

Install uv:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Install DVC with S3 support:
```bash
uv tool install "dvc[s3]"
```

Sync uv with appropriate python packages:
```bash
uv sync --extra cu124 --locked
```
Change `cu124` to `cu129` if the CUDA version is 12.9 on the system.

After this sync, remember to always either use the `--extra cu124` flag or use
`--no-sync`, so `uv` doesn't try to re-install torch with a newer version. Eg.

```bash
uv run --no-sync python
```

Install the object detection module in an editable state:
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

Here is a visual describing all the components:

```mermaid
flowchart TD

    %% =========================
    %% RAW DATA
    %% =========================
    subgraph RAW["① Raw data ingestion"]
        direction LR

        S3["☁️ S3<br/>Label Studio exports"]
        RAWJSON["📁 update_raw<br/><small>Sync Label Studio JSON</small>"]
        INDEX["🗂️ index_labelstudio_sites<br/><small>Group JSON exports by site</small>"]
        METAALL["📋 build_video_metadata_index_all<br/><small>Global video metadata index</small>"]

        S3 --> RAWJSON
        RAWJSON --> INDEX
        RAWJSON --> METAALL
    end


    %% =========================
    %% PER SITE
    %% =========================
    subgraph SITE["② Per-site processing — foreach data.sites"]
        direction TB

        INPUT["🏷️ build_model_input@SITE<br/><small>Label Studio → YOLO labels<br/>frame sampling + negatives</small>"]

        STATS["📊 plot_site_class_stats@SITE<br/><small>Dataset inspection / QA</small>"]

        SPLIT["✂️ split_data@SITE<br/><small>Train / val / test split</small>"]

        METASITE["📋 build_video_metadata_index@SITE<br/><small>Filter metadata to site</small>"]

        PACK["📦 pack_split_dataset@SITE<br/><small>Extract images + labels → tar shards</small>"]

        INPUT --> STATS
        INPUT --> SPLIT
        INPUT --> PACK
        METASITE --> PACK
        SPLIT --> PACK
    end


    INDEX --> INPUT
    METAALL --> METASITE


    %% =========================
    %% NEGATIVES
    %% =========================
    subgraph NEG["③ Shared negative examples"]
        direction LR

        CONDITIONS["🌊 Water-condition metadata"]
        NEGATIVE["🚫 build_condition_negatives<br/><small>Generate condition-negative labels</small>"]

        CONDITIONS --> NEGATIVE
    end

    NEGATIVE --> SPLIT
    NEGATIVE --> PACK


    %% =========================
    %% CACHE
    %% =========================
    subgraph CACHE["♻️ Frame reuse cache"]
        direction TB

        SITECACHE["📦 Previous SITE shards<br/><small>Preferred cache</small>"]
        LEGACYCACHE["🗄️ Legacy combined shards<br/><small>Fallback cache</small>"]
        GLACIER["❄️ S3 / Glacier source MP4<br/><small>Only needed for uncached frames</small>"]

        SITECACHE -. reuse JPEG .-> PACK
        LEGACYCACHE -. reuse JPEG .-> PACK
        GLACIER -. download missing frames .-> PACK
    end


    %% =========================
    %% MERGE
    %% =========================
    subgraph ASSEMBLY["④ Dataset assembly"]
        direction TB

        SITES["📦 dataset_sharded/sites/<site><br/><small>Independent cached site datasets</small>"]

        MERGE["🔀 merge_packed_site_datasets<br/><small>Merge site manifests</small>"]

        GLOBAL["📑 Global dataset manifests<br/><small>train / val / test / data.yaml</small>"]

        SITEFILTER["🎯 make_site_manifests<br/><small>Select exp.train_sites / val_sites / test_sites</small>"]

        SMALL["🧪 make_train_small<br/><small>30k-sample tuning subset</small>"]

        SITES --> MERGE
        MERGE --> GLOBAL
        GLOBAL --> SITEFILTER
        SITEFILTER --> SMALL
    end

    PACK --> SITES


    %% =========================
    %% MATERIALIZE DATASET
    %% =========================
    subgraph WORKDIR["⑤ Materialize training workdir"]
        direction TB

        UNPACK["📂 unpack_split_dataset<br/><small>Unpack active site tar shards</small>"]

        CROP["✂️ Site preprocessing<br/><small>e.g. Klukshu top-half crop</small>"]

        REWRITE["📝 rewrite_manifest<br/><small>Write absolute train/val/test paths</small>"]

        YOLODIR["📁 yolo_workdir<br/><small>Final Ultralytics dataset</small>"]

        UNPACK --> CROP
        CROP -. operational order .-> REWRITE
        REWRITE --> YOLODIR
    end

    SITES --> UNPACK
    GLOBAL --> UNPACK
    SITEFILTER --> REWRITE
    SMALL --> REWRITE


    %% =========================
    %% TRAINING
    %% =========================
    subgraph TRAINING["⑥ Model development"]
        direction LR

        TUNE["🔧 tune_yolo<br/><small>Ray Tune on train_small</small>"]

        TRAIN["🚀 train_yolo_best<br/><small>Full dataset + best hyperparameters</small>"]

        MODEL["🧠 best.pt"]

        TUNE --> TRAIN
        TRAIN --> MODEL
    end

    YOLODIR --> TUNE
    YOLODIR --> TRAIN


    %% =========================
    %% EVALUATION
    %% =========================
    subgraph EVALUATION["⑦ Site-based evaluation"]
        direction LR

        EVALSET["🎯 make_site_eval_workdir<br/><small>Select exp.test_sites</small>"]

        EVAL["📈 evaluate<br/><small>mAP / class AP / plots</small>"]

        RESULTS["📊 Evaluation results"]

        EVALSET --> EVAL
        EVAL --> RESULTS
    end

    GLOBAL --> EVALSET
    MODEL --> EVAL


    %% =========================
    %% STYLING
    %% =========================
    classDef raw fill:#e8f4fd,stroke:#2980b9,stroke-width:2px,color:#111;
    classDef site fill:#eafaf1,stroke:#27ae60,stroke-width:2px,color:#111;
    classDef cache fill:#fff4e6,stroke:#e67e22,stroke-width:2px,color:#111;
    classDef assembly fill:#f4ecf7,stroke:#8e44ad,stroke-width:2px,color:#111;
    classDef training fill:#fdebd0,stroke:#d35400,stroke-width:2px,color:#111;
    classDef eval fill:#f9ebea,stroke:#c0392b,stroke-width:2px,color:#111;

    class S3,RAWJSON,INDEX,METAALL raw;
    class INPUT,STATS,SPLIT,METASITE,NEGATIVE,CONDITIONS site;
    class PACK,SITECACHE,LEGACYCACHE,GLACIER cache;
    class SITES,MERGE,GLOBAL,SITEFILTER,SMALL,UNPACK,CROP,REWRITE,YOLODIR assembly;
    class TUNE,TRAIN,MODEL training;
    class EVALSET,EVAL,RESULTS eval;
```

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

#### Issue: Object is of storage class GLACIER

This happens when the videos we are trying to download have been
archived into GLACIER storage. We can restore these temporarily
with the following bash script.

Capture the `repro` command into a logfile:

```
dvc repro pack_split_dataset 2>&1 | tee pack.log
```

Submit restore requests:
```
./scripts/restore_glacier_from_log.sh request pack.log
```

By default it will be BULK (5-12 hours process) and for 3 days.

Explicitly:
```bash
./scripts/restore_glacier_from_log.sh request pack.log 3 Bulk
```

Once the requests have been sent, use the same script to check the status:

```
./scripts/restore_glacier_from_log.sh status pack.log
```

The last line should say when all the objects are ready for download.

### Plot AP50 by site

To evaluate over all test sites, run the following command:

```bash
uv run --extra cu124 ./scripts/run_site_eval_experiments.py --queue --run-queue
```
Replace cu124 with your appropriate CUDA version if necessary.

Add `--dry-run` to test the command first.

They can be plotted after using
```bash
./scripts/plot-all-eval.sh "Full Model AP50"
```

This creates an HTML in `dvc_plots` with the plots.

Run a simple http server and connect to it through SSH tunnel
```bash
cd dvc_plots
python -m http.server
```
