#!/usr/bin/env python
import sys
import os
from pathlib import Path

# MOT GT Seq
# <Frame num>,<Identity num>,<box left>,<box top>,<box width>,<box height>,<confidence>,<class>,<visibility>
# Must delete labels_with_ids folder if already exists

def create_data_list(dataset_path):
  imgs_path = os.path.join(dataset_path, 'images')
  root_path = os.path.basename(os.path.normpath(dataset_path))
  rel_imgs_path = os.path.join(root_path, 'images')
  img_filenames = os.listdir(imgs_path)

  with open(os.path.join(dataset_path, 'salmon.train'), 'w') as f:
    f.writelines(f"{os.path.join(rel_imgs_path, filename)}\n" for filename in img_filenames)

def main():
  height = 1080
  width = 1920

  if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} <path/to/mot_seq_folder>")
    return


  dataset_path = sys.argv[1]
  gt_file_path = os.path.join(dataset_path, "gt", "gt.txt")
  label_out_path = os.path.join(dataset_path, "labels_with_ids")
  Path(label_out_path).mkdir(parents=True, exist_ok=False)

  create_data_list(dataset_path)

  print("Reading", gt_file_path)
  with open(gt_file_path) as f:
    for line in f:
      parts = line.strip().split(',')
      # Frame name formatted as <task ID><6 digit frame ID>
      frame_name = parts[0]
      track_id = parts[1]
      x = float(parts[2])
      y = float(parts[3])
      box_width = float(parts[4])
      box_height = float(parts[5])
      class_id = parts[7]
      #print(frame_name, track_id, box_left, box_top, box_width, box_height, class_id)

      task_id = frame_name[:-6]
      new_track_id = f"{task_id}{track_id}" # Task IDs should be unique

      x_center = x + box_width / 2.0
      y_center = y + box_height / 2.0

      # JDE currently can only do one class tracking
      label_str = f"{class_id} {new_track_id} {x_center / width} {y_center / height} {box_width / width} {box_height / height}\n"
      with open(os.path.join(label_out_path, f"{frame_name}.txt"), 'a') as out:
          out.write(label_str)

main()
