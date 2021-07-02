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

When we have JDE annotations ready, we can start training our model. We need to git clone Towards-Realtime-MOT repository on our computer.

## Git Clone Towards-Realtime-MOT

Note that we want to git clone our salmon version MOT repository. Therefore, please git clone from this GitHub repository, and then switch to **Salmon branch**:

[Salmon-Computer-Vision/Towards-Realtime-MOT](https://github.com/Salmon-Computer-Vision/Towards-Realtime-MOT/tree/salmon)

## Training Set Up

Once we have the JDE annotations generated from the previous command, please move the following three files to parent folder of merged_mot_gt folder:

- salmon.train
- salmon.val
- salmon.test

For example,

```bash
mv ~/salmon-computer-vision/utils/merged_mot_gt/salmon.train ~/salmon-computer-vision/utils
```

so that the image paths in the three salmon files match the actual image path.

Then, we need to modify ~/Towards-Realtime-MOT/cfg/ccmcpe.json to point to the training data. An example of ccmcpe.json is:

```json
{
    "root":"/home/ycchou/salmon-computer-vision/utils/",
    "train":
    {
        "fish":"/home/ycchou/salmon-computer-vision/utils/salmon.train"
    },
    "test_emb":
    {
        "fish":"/home/ycchou/salmon-computer-vision/utils/salmon.val"
    },
    "test":
    {
        "fish":"/home/ycchou/salmon-computer-vision/utils/salmon.val"
    }
}
```

## Run [train.py](http://train.py) script

Make sure you have installed CUDA on your system. If you did not install CUDA, you will likely encounter Found no NVIDIA driver error. Please check the troubleshooting section to install CUDA for your system.

Please run the [train.py](http://train.py) script to start training the model. Reduce batch size if you GPU memory is not enough. You would likely encounter RuntimeError: CUDA out of memory if your batch size is too high.

```
python train.py --batch-size 6 --img-size 576 320
```

After the training process is finished, we can find the trained weights at:

```json
Towards-Realtime-MOT\weights\{date folder}\latest.pt
```

## Troubleshooting

### RuntimeError: Found no NVIDIA driver on your system.

```
RuntimeError: Found no NVIDIA driver on your system. Please check that you have an NVIDIA GPU and installed a driver from http://www.nvidia.com/Download/index.aspx
```

Make sure we have installed CUDA on our system. Please check this page to install CUDA on your system.

[Running CUDA](https://docs.nvidia.com/cuda/wsl-user-guide/index.html#running-cuda)

### E: Unable to locate package cuda-toolkit-11-0

```
E: Unable to locate package cuda-toolkit-11-0
```

It is likely that the apt-key cuda.list does not have the right version of the system. For example,

```
apt-key adv --fetch-keys http://developer.download.nvidia.com/compute/cuda/repos/ubuntu1804/x86_64/7fa2af80.pub
```

If you are using Ubuntu 20.04, please replace ubuntu1804 with ubuntu2004.

Also, make sure you install the right version of toolkit for your system version. Check this page to find the correct version of toolkit:

[Installation Guide Linux :: CUDA Toolkit Documentation](https://docs.nvidia.com/cuda/cuda-installation-guide-linux/index.html#package-manager-metas)

### RuntimeError: CUDA out of memory.

It is likely that the batch size you specified in the train command is too high. Please try to reduce the batch size and try again.
