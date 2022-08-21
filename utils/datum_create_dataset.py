#!/usr/bin/env python3

import os
import subprocess
import datumaro as dm

### Required:
# Datumaro
# unzip

DATUM = 'datum'
def extract_frames(proj_path, name, vid_path):
    # Extract frames to the project folder
    dest_path = os.path.join(proj_path, name)
    subprocess.run([DATUM, 'util', 'split_video', '-i', vid_path, '--image-ext=.png', "--name-pattern='frame_%06d'", '-o', dest_path])

    name = os.path.splitext(os.path.basename(vid_path))[0]
# For each video
# Extract frames into a folder
# Add the folder as the `image_dir` format
# Unzip corresponding annotation file into a folder
# Add the folder as the `cvat` format
# Rename `annotations.xml` to `default.xml`
# Merge the two folders (Saving the images)
# Delete the frames and cvat folders
# Export as `mot_seq_gt`
# Generate a seqinfo.ini file
