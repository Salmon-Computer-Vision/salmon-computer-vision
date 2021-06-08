# Salmon Computer Vision Project

Followed [this TF2 Detection API tutorial](https://tensorflow-object-detection-api-tutorial.readthedocs.io/en/latest/install.html) extensively.

## Run MOT Inference Model

We can run MOT inference model to detect fish from frames. 

Please read this [document](docs/run_mot_inference.md) for further details.

## Create CVAT Tasks Automatically

### Run make_cvat_tasks.sh

We need to run make_cvat_tasks.sh script at utils folder to automatically create cvat tasks on our cvat server.

Please read this [document](docs/run_make_cvat_tasks.md) for further details about running **make_cvat_tasks.sh** script.

### Run dump_cvat.sh

After running make_cvat_tasks.sh, we will have tasks that are already labelled on cvat server.

Now, we want to dump those tasks to our local computer.

Please follow this [document](docs/run_dump_cvat.md) to run dump_cvat.sh script.

### Run download_frames.sh

The download_frames.sh uses the cvat plugin to download the frames specified by the xpath_filt (Or just all annotated frames) and renames them to differentiate the task IDs for easy merging.

Please follow this [document](docs/run_download_frames.md) to run download_frames.sh script.
