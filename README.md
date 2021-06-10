# Salmon Computer Vision Project

Followed [this TF2 Detection API tutorial](https://tensorflow-object-detection-api-tutorial.readthedocs.io/en/latest/install.html) extensively.

# Run MOT Inference Model

We can run MOT inference model to detect fish from frames. 

Please read this [document](docs/run_mot_inference.md) for further details.

# Train Model

To train the model, we need to run some scripts to prepare training data. Please follow the following sections to run each of scripts.

## Run make_cvat_tasks.sh

We need to run make_cvat_tasks.sh script at utils folder to automatically create cvat tasks on our cvat server.

Please read this [document](docs/run_make_cvat_tasks.md) for further details about running **make_cvat_tasks.sh** script.

## Run dump_cvat.sh

After running make_cvat_tasks.sh, we will have tasks that are already labelled on cvat server.

Now, we want to dump those tasks to our local computer.

Please follow this [document](docs/run_dump_cvat.md) to run dump_cvat.sh script.

## Run download_frames.sh

The download_frames.sh uses the cvat plugin to download the frames specified by the xpath_filt (Or just all annotated frames) and renames them to differentiate the task IDs for easy merging.

Please follow this [document](docs/run_download_frames.md) to run download_frames.sh script.

## Run merge_filt.sh

This script merges the dumped annotations from previous script and split them into training set, validation set and test set.

Please follow this [document](docs/run_merge_filt.md) to run merge_filt.sh script.

## Export project to MOT Seq GT format

After we have the merged result, we want to export the **merged** folder produced by the merge_filt.sh script to MOT Seq GT.

```
datum export -p merged -o merged_mot_gt -f mot_seq_gt -- --save-images
```

## Run the python script convert_gt_jde.py

After we have MOT Seq GT format annotations, we want to convert them to JDE format. Then, we want to split data into training, validation and test dataset.

Please follow this [document](docs/run_convert_gt_jde.md) to run convert_gt_jde.py script.

## At the end of running the above scripts

After running the above scripts, we have created CVAT tasks and converted the annotations to JDE format.

Therefore, we can use the JDE format data to train the model.
