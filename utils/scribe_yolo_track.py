#!/usr/bin/env python
import sys
import glob, os
import argparse

def insert_track_id(label_file, track_ids):
  labels_with_track = []
  with open(label_file, 'r') as yolo_f:
    labels = yolo_f.readlines()

    for i, label in enumerate(labels):
      split_label = label.split()
      if len(split_label) < 6:
        split_label.insert(1, track_ids[i]) # Insert track ID into label
      else:
        print(f'{label_file} should have track ID already')
      labels_with_track.append(' '.join(split_label) + '\n')

  with open(label_file, 'w') as yolo_f:
    yolo_f.writelines(labels_with_track)

def main(args):
  mot_labels_path = os.path.join(args.mot_jde_dir, 'labels_with_ids')
  yolo_train_labels_path = os.path.join(args.yolo_dir, 'obj_train_data')
  yolo_valid_labels_path = os.path.join(args.yolo_dir, 'obj_valid_data')

  for label_file in glob.glob(os.path.join(mot_labels_path, '*')):

    track_ids = []
    # Format: [class] [track_id] [x] [y] [width] [height]
    with open(label_file, 'r') as mot_f:
      mot_labels = mot_f.readlines()
      for label in mot_labels:
        track_ids.append(label.split()[1])

    label_filename = os.path.splitext(os.path.basename(label_file))[0]
    task_id = label_filename[:-6]
    frame_id = label_filename[-6:]
    yolo_label_filename = f'{task_id}_{frame_id}.txt'

    train_label = os.path.join(yolo_train_labels_path, yolo_label_filename)
    valid_label = os.path.join(yolo_valid_labels_path, yolo_label_filename)
    if os.path.exists(train_label):
      assert not os.path.exists(valid_label)
      insert_track_id(train_label, track_ids)
    elif os.path.exists(valid_label):
      insert_track_id(valid_label, track_ids)
    else:
      print(f'label file {yolo_label_filename} not found. Skipping...')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Transcribe track IDs to yolo format from MOT JDE format.')
  parser.add_argument('mot_jde_dir')
  parser.add_argument('yolo_dir')

  args = parser.parse_args()
  main(args)
