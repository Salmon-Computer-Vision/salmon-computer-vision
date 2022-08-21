#!/usr/bin/env python3

import os
import os.path as osp
import subprocess
import datumaro as dm
import argparse
import logging as log

import pandas as pd

log.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=log.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

### Required:
# Datumaro
# unzip

class VidDataset:
    DATUM = 'datum'
    PREFIX_VID = 'vid_'
    PREFIX_CVAT = 'cvat_'
    dataset = None

    def __init__(self, vid_path: str, proj_path: str, anno_folder: str):
        self.extract_frames(vid_path)

        self.proj_path = proj_path
        self.anno_folder = anno_folder

    def extract_frames(self, vid_path: str):
        # Extract frames to the project folder
        #dest_path = osp.join(self.proj_path, self.PREFIX_VID + name)
        log.info("Importing video...")

        self.dataset = dm.Dataset.import_from(
            vid_path,
            "video_frames",
            name_pattern='frame_%06d',
        )

        #vid_data.export(format="image_dir", save_dir=dest_path, image_ext=args.image_ext)

    def import_zipped_anno(self, name: str, anno_zip_path: str):
        dest_path = osp.join(self.anno_folder, self.PREFIX_CVAT + name)
        log.info("Unzipping and importing CVAT...")
        subprocess.run(['unzip', '-o', '-d', dest_path, anno_zip_path])

        self.dataset.import_from(dest_path, "cvat")

    def export_datum(self, name: str):
        log.info("Exporting to datumaro...")
        dest_path = osp.join(self.proj_path, name)
        self.dataset.export(dest_path, 'datumaro', save_images=True)

def main(args):
    df = pd.read_csv(args.csv_vids)
    os.makedirs(args.anno_dir, exist_ok=True)
    os.makedirs(args.proj_path, exist_ok=True)
    for _, row in df.iterrows():
        vid_data = VidDataset(row.vid_path, args.proj_path, args.anno_dir)
        name = osp.splitext(osp.basename(row.anno_path))[0]
        vid_data.import_zipped_anno(name, row.anno_path)
        vid_data.export_datum(name)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Combine videos and annotations and exports them into a Datumaro project.')

    parser.add_argument('csv_vids', help='CSV file of video and annotation .zip filepaths. Must have the columns "vid_path" and "anno_path"')
    parser.add_argument('--anno-dir', default='annos', help='Annotations destination folder')
    parser.add_argument('--proj-path', default='datum_proj', help='Datumaro project destination folder')
    parser.set_defaults(func=main)

    args = parser.parse_args()
    args.func(args)

# For each video
# Create a datumaro project
# Extract frames into a folder
# Add the folder as the `image_dir` format
# Unzip corresponding annotation file into a folder
# Add the folder as the `cvat` format
# Rename `annotations.xml` to `default.xml`
# Merge the two folders (Saving the images)
# Delete the frames and cvat folders
# Export as `mot_seq_gt`
# Generate a seqinfo.ini file
