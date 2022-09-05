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
import configparser
from benedict import benedict

import pandas as pd

import cv2

import datumaro as dm
from datumaro.plugins.transforms import Rename
from datumaro.components.operations import IntersectMerge

log.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=log.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

DATUM = 'datum'
PREFIX_VID = 'vid_'
PREFIX_CVAT = 'cvat_'
XML_ANNOTATIONS = 'annotations.xml'
XML_DEFAULT = 'default.xml'

DUP_LABELS_MAPPING = {
        'White Fish': 'Whitefish',
        'Bull Trout': 'Bull'
        }

class VidDataset:
    # Datumaro datasets
    vid_dataset = None
    cvat_dataset = None
    dataset = None

    # seqinfo.ini
    imDir = 'img1'
    frameRate = -1
    seqLength = -1
    imWidth = -1
    imHeight = -1
    imExt = '.jpg'

    def __init__(self, name: str, vid_path: str, args):
        self.proj_path = args.proj_path
        self.anno_path = args.anno_path
        self.transform_path = args.transform_path
        self.mot_path = args.mot_path

        self.extract_frames(name, vid_path)

    def extract_frames(self, name: str, vid_path: str, overwrite=False):
        # Get data for the seqinfo.ini
        video = cv2.VideoCapture(vid_path)
        self.frameRate = video.get(cv2.CAP_PROP_FPS)
        self.imWidth = video.get(cv2.CAP_PROP_FRAME_WIDTH)
        self.imHeight = video.get(cv2.CAP_PROP_FRAME_HEIGHT)

        # Extract frames to the project folder
        dest_path = osp.join(self.anno_path, PREFIX_VID + name)

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

        vid_data.export(format="image_dir", save_dir=dest_path, image_ext=self.imExt)

        self._import_image_dir(dest_path)

    def _import_image_dir(self, dest_path: str):
        _, _, files = next(os.walk(dest_path))
        self.seqLength = len(files)

        self.vid_dataset = dm.Dataset.import_from(
                dest_path,
                "image_dir"
                )

    def import_zipped_anno(self, name: str, anno_zip_path: str, overwrite=False):
        dest_path = osp.join(self.anno_path, PREFIX_CVAT + name)
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skipping unzip {dest_path}")
            self.cvat_dataset = dm.Dataset.import_from(dest_path, "cvat")
            return

        log.info("Unzipping and importing CVAT...")
        subprocess.run(['unzip', '-o', '-d', dest_path, anno_zip_path])

        # Rename to the default, so the annotations can be matched with the video frames
        os.rename(osp.join(dest_path, XML_ANNOTATIONS), osp.join(dest_path, XML_DEFAULT))
        self.cvat_dataset = dm.Dataset.import_from(dest_path, "cvat")

    def _transform(self, name: str, src_path: str, overwrite=False):
        dest_path = osp.join(self.transform_path, name.lower()) # Must be lowercase due to datumaro restrictions
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skipping transform {dest_path}")
            return

        log.info(f"Renaming video frames to {dest_path}")
        subprocess.run([DATUM, 'transform', '-t', 'rename', '-o', dest_path,
            f"{src_path}:datumaro", '--', '-e', f"|^frame_|{name}_|"])

    def export_datum(self, name: str, overwrite=False):
        dest_path = osp.join(self.proj_path, name.lower()) # Must be lowercase due to datumaro restrictions
        #self.dataset = dm.Dataset.from_extractors(self.vid_dataset, self.cvat_dataset)
        self.dataset = IntersectMerge()([self.vid_dataset, self.cvat_dataset])
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skipping datum export {dest_path}")
            self._transform(name, dest_path)
            return

        log.info(f"Exporting as datumaro to {dest_path}")
        self.dataset.export(dest_path, 'datumaro', save_images=True)

        self._transform(name, dest_path)

    def export_mot(self, name: str, overwrite=False):
        exp_format = 'mot_seq_gt'
        dest_path = osp.join(self.mot_path, name)
        if not overwrite and osp.exists(dest_path):
            log.info(f"Exists. Skipping export {dest_path}")
            return

        log.info(f"Exporting as {exp_format} to {dest_path}")
        self.dataset.export(dest_path, exp_format, save_images=True)
        
        self._gen_seqinfo(name, dest_path)

    def _gen_seqinfo(self, name: str, dest_path: str):
        # Generate seqinfo.ini file
        seq_path = osp.join(dest_path, 'seqinfo.ini')

        d = benedict()
        d['Sequence'] = {}
        seq = d['Sequence']

        seq['name'] = name
        seq['imDir'] = self.imDir
        seq['frameRate'] = self.frameRate
        seq['seqLength'] = self.seqLength
        seq['imWidth'] = self.imWidth
        seq['imHeight'] = self.imHeight
        seq['imExt'] = self.imExt

        d.to_ini(filepath=seq_path)

def filename_to_name(filename):
    return filename.replace(' ', '_')

def export_vid(row_tuple):
    row = row_tuple[1]
    name = filename_to_name(row.filename)
    vid_data = VidDataset(name, row.vid_path, args)
    vid_data.import_zipped_anno(name, row.anno_path)
    vid_data.export_datum(name)
    vid_data.export_mot(name)

def merge_dataset(row_tuples, transform_path: str):
    """
    Merge the separated video datasets into one to deal with inconsistent labels
    """
    log.info('Merging transformed dataset...')
    temp_path = transform_path[:-1] if transform_path.endswith('/') else transform_path
    dest_path = f'{temp_path}_merged'

    datasets_paths = [osp.join(transform_path, filename_to_name(row.filename).lower()) for _, row in row_tuples]
    datasets = [dm.Dataset.import_from(data_path, "datumaro") for data_path in datasets_paths]
    dataset_merged = IntersectMerge()(datasets)

    # Fix duplicate labels
    dataset_merged.transform('remap_labels', mapping=DUP_LABELS_MAPPING)

    dataset_merged.export(format='datumaro', save_dir=dest_path)


"""
Split the merged dataset into individual videos again
"""

def main(args):
    df = pd.read_csv(args.csv_vids)
    os.makedirs(args.anno_path, exist_ok=True)
    os.makedirs(args.proj_path, exist_ok=True)
    os.makedirs(args.transform_path, exist_ok=True)
    os.makedirs(args.mot_path, exist_ok=True)

    jobs_pool = Pool(int(args.jobs))
    row_tuples = df.iterrows()

    jobs_pool.map(export_vid, row_tuples)

    jobs_pool.close()
    jobs_pool.join()

    merge_dataset(df.iterrows(), args.transform_path)

if __name__ == '__main__':
    configparser.ConfigParser.optionxform = str

    parser = argparse.ArgumentParser(description='Combine videos and annotations and exports them into a Datumaro project.')

    parser.add_argument('csv_vids', help='CSV file of video and annotation .zip filepaths. Must have the columns `filename`, `vid_path`, and `anno_path`. `filename` must be a unique index.')
    parser.add_argument('--anno-path', default='annos', help='Annotations destination folder. Default: annos')
    parser.add_argument('--proj-path', default='datum_proj', help='Datumaro project destination folder. Default: datum_proj')
    parser.add_argument('--transform-path', default='datum_proj_transform', help='Datumaro project transform destination folder. Default: datum_proj_transform')
    parser.add_argument('--mot-path', default='export_mot', help='MOT path to export to. Default: export_mot')
    parser.add_argument('-j', '--jobs', default='4', help='Number of jobs to run. Default: 4')
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
