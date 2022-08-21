#!/usr/bin/env python3

### Required:
# Datumaro
# unzip

import os
import os.path as osp
import subprocess
import argparse
import logging as log
from multiprocessing import Pool

import pandas as pd

import datumaro as dm
from datumaro.plugins.transforms import Rename

log.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=log.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

DATUM = 'datum'
PREFIX_VID = 'vid_'
PREFIX_CVAT = 'cvat_'
XML_ANNOTATIONS = 'annotations.xml'
XML_DEFAULT = 'default.xml'

class VidDataset:
    vid_dataset = None
    cvat_dataset = None

    def __init__(self, name: str, vid_path: str, proj_path: str, anno_folder: str, transform_path: str):
        self.proj_path = proj_path
        self.anno_folder = anno_folder
        self.transform_path = transform_path

        self.extract_frames(name, vid_path)

    def extract_frames(self, name: str, vid_path: str, overwrite=False):
        # Extract frames to the project folder
        dest_path = osp.join(self.anno_folder, PREFIX_VID + name)
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skip extracting {dest_path}")
            self._import_image_dir(dest_path)
            return

        log.info(f"Extracting frames {vid_path}")

        vid_data = dm.Dataset.import_from(
            vid_path,
            "video_frames",
            name_pattern='frame_%06d',
        )

        vid_data.export(format="image_dir", save_dir=dest_path, image_ext='.jpg')

        self._import_image_dir(dest_path)

    def _import_image_dir(self, dest_path: str):
        self.vid_dataset = dm.Dataset.import_from(
                dest_path,
                "image_dir"
                )

    def import_zipped_anno(self, name: str, anno_zip_path: str):
        dest_path = osp.join(self.anno_folder, PREFIX_CVAT + name)
        log.info("Unzipping and importing CVAT...")
        subprocess.run(['unzip', '-o', '-d', dest_path, anno_zip_path])

        # Rename to the default, so the annotations can be matched with the video frames
        os.rename(osp.join(dest_path, XML_ANNOTATIONS), osp.join(dest_path, XML_DEFAULT))
        self.cvat_dataset = dm.Dataset.import_from(dest_path, "cvat")

    def _transform(self, name: str, src_path: str):
        #dataset = dm.Dataset.import_from(dest_path, 'datumaro')
        dest_path = osp.join(self.transform_path, name)
        log.info(f"Renaming video frames to {dest_path}")
        subprocess.run([DATUM, 'transform', '-t', 'rename', '-o', dest_path,
            f"{src_path}:datumaro", '--', '-e', f"|^frame_|{name}_|"])

    def export_datum(self, name: str, overwrite=False):
        dest_path = osp.join(self.proj_path, name.lower()) # Must be lowercase due to datumaro restrictions
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skipping {dest_path}")
            self._transform(name, dest_path)
            return

        log.info(f"Exporting as datumaro to {dest_path}")
        dataset = dm.Dataset.from_extractors(self.vid_dataset, self.cvat_dataset)
        dataset.export(dest_path, 'datumaro', save_images=True)

        self._transform(name, dest_path)

def export_vid(row_tuple):
    row = row_tuple[1]
    name = osp.splitext(osp.basename(row.anno_path))[0]
    vid_data = VidDataset(name, row.vid_path, args.proj_path, args.anno_dir, args.transform_path)
    vid_data.import_zipped_anno(name, row.anno_path)
    vid_data.export_datum(name)

def main(args):
    df = pd.read_csv(args.csv_vids)
    os.makedirs(args.anno_dir, exist_ok=True)
    os.makedirs(args.proj_path, exist_ok=True)
    os.makedirs(args.transform_path, exist_ok=True)

    jobs_pool = Pool(int(args.jobs))
    row_tuples = df.iterrows()

    jobs_pool.map(export_vid, row_tuples)

    jobs_pool.close()
    jobs_pool.join()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Combine videos and annotations and exports them into a Datumaro project.')

    parser.add_argument('csv_vids', help='CSV file of video and annotation .zip filepaths. Must have the columns "vid_path" and "anno_path"')
    parser.add_argument('--anno-dir', default='annos', help='Annotations destination folder')
    parser.add_argument('--proj-path', default='datum_proj', help='Datumaro project destination folder')
    parser.add_argument('--transform-path', default='datum_proj_transform', help='Datumaro project transform destination folder')
    parser.add_argument('-j', '--jobs', default='4', help='Number of jobs to run')
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
