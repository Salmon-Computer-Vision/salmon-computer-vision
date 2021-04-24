#!/usr/bin/env python
import sys
import glob, os
import numpy as np
import random
import argparse
from pathlib import Path

from utils import deserialize_anno

# MOT GT Seq
# <Frame num>,<Identity num>,<box left>,<box top>,<box width>,<box height>,<confidence>,<class>,<visibility>
# Must delete labels_with_ids folder if already exists
images_folder = 'images'

def create_data_list(args):
  if args.all:
    create_data_list_all(args.data_dir)
  else:
    create_data_list_task(args.data_dir)

def create_data_list_all(dataset_path):
  imgs_path = os.path.join(dataset_path, images_folder)
  set_name = os.path.basename(os.path.normpath(dataset_path))
  rel_imgs_path = os.path.join(set_name, images_folder)
  img_filenames = os.listdir(imgs_path)

  random.shuffle(img_filenames)
  train, val, test = np.split(img_filenames, [int(len(img_filenames)*0.7), int(len(img_filenames)*0.85)])
  print(len(train), len(val), len(test))

  os.chdir(os.path.join(dataset_path, '..'))
  def write_paths(out_path, path_list):
    with open(os.path.join(dataset_path, out_path), 'w') as f:
      for filename in path_list:
        f.write(os.path.join(rel_imgs_path,  f"{filename}\n"))

  print("Writing training image list...")
  write_paths('salmon.train', train)

  print("Writing validation image list...")
  write_paths('salmon.val', val)

  print("Writing testing image list...")
  write_paths('salmon.test', test)

def create_data_list_task(dataset_path):
  imgs_path = os.path.join(dataset_path, images_folder)
  set_name = os.path.basename(os.path.normpath(dataset_path))
  rel_imgs_path = os.path.join(set_name, images_folder)
  img_filenames = os.listdir(imgs_path)

  task_ids = list(dict.fromkeys([name[:-10] for name in img_filenames]))

  random.shuffle(task_ids)
  train, val, test = np.split(task_ids, [int(len(task_ids)*0.7), int(len(task_ids)*0.85)])
  print(len(train), len(val), len(test))

  os.chdir(os.path.join(dataset_path, '..'))
  def write_paths(task, f):
      img_paths = glob.glob(os.path.join(rel_imgs_path, f"{task}*"))
      img_paths.sort()
      f.writelines(f"{rel_filename}\n" for rel_filename in img_paths)

  print("Writing training image list...")
  with open(os.path.join(dataset_path, 'salmon.train'), 'w') as f:
    for task in train:
      write_paths(task, f)

  print("Writing validation image list...")
  with open(os.path.join(dataset_path, 'salmon.val'), 'w') as f:
    for task in val:
      write_paths(task, f)

  print("Writing testing image list...")
  with open(os.path.join(dataset_path, 'salmon.test'), 'w') as f:
    for task in test:
      write_paths(task, f)

def convert_to_jde(args):
  height = 1080
  width = 1920

  dataset_path = args.data_dir
  gt_file_path = os.path.join(dataset_path, "gt", "gt.txt")
  label_out_path = os.path.join(dataset_path, "labels_with_ids")

  Path(label_out_path).mkdir(parents=True, exist_ok=False)

  print("Reading", gt_file_path)
  with open(gt_file_path) as f:
    cur_track_id = -1
    last_task_id = -1
    max_track_id = -1
    for line in f:
      parts = line.strip().split(',')
      frame_name, track_id, x, y, box_width, box_height, class_id = deserialize_anno(parts)

      track_id = int(track_id) - 1 # Offset for JDE format
      task_id = int(frame_name[:-6])

      if track_id > max_track_id:
        max_track_id = track_id

      if not last_task_id == task_id:
        cur_track_id += max_track_id + 1
        last_task_id = task_id
        max_track_id = -1

      new_track_id = track_id + cur_track_id

      x_center = x + box_width / 2.0
      y_center = y + box_height / 2.0

      # JDE currently can only do one class tracking
      #label_str = f"{class_id} {new_track_id} {x_center / width} {y_center / height} {box_width / width} {box_height / height}\n"
      label_str = f"0 {new_track_id} {x_center / width} {y_center / height} {box_width / width} {box_height / height}\n"
      with open(os.path.join(label_out_path, f"{frame_name}.txt"), 'a') as out:
          out.write(label_str)

  print("Renaming img1 to", images_folder);
  os.rename(os.path.join(dataset_path, 'img1'), os.path.join(dataset_path, images_folder))

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Convert MOT Seq to JDE and split dataset into train, val, test sets')
  subp = parser.add_subparsers()

  split_p = subp.add_parser('split')
  split_p.add_argument('-a', '--all', action='store_true', help='Shuffle all the images in the list disregarding video ID')
  split_p.add_argument('data_dir')
  split_p.set_defaults(func=create_data_list)

  convert_p = subp.add_parser('convert')
  convert_p.add_argument('data_dir')
  convert_p.set_defaults(func=convert_to_jde)

  args = parser.parse_args()
  args.func(args)
