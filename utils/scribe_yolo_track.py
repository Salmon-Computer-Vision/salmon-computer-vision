#!/usr/bin/env python
import sys
import glob, os
import argparse

def main(args):
  mot_labels_path = os.path.join(args.mot_jde_dir, 'labels_with_ids')
  yolo_train_labels_path = os.path.join(args.yolo_dir, 'obj_train_data')
  yolo_valid_labels_path = os.path.join(args.yolo_dir, 'obj_valid_data')

  for label_file in glob.glob(os.path.join(mot_labels_path, '*')):
    with open(label_file, 'r'):
      label_filename = os.path.splitext(os.path.basename(label_file))[0]
      task_id = label_filename[:-6]
      frame_id = label_filename[-6:]
      yolo_label_filename = f'{task_id}_{frame_id}.txt'

      train_label = os.path.join(yolo_train_labels_path, yolo_label_filename)
      valid_label = os.path.join(yolo_valid_labels_path, yolo_label_filename)
      if os.path.exists(train_label):
        assert not os.path.exists(valid_label)
        with open(train_label, 'rw'):
          for 
      else if os.path.exists(valid_label):

      else:
        raise FileNotFoundError(f'label file {yolo_label_filename} not found')


if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Transcribe track IDs to yolo format from MOT JDE format.')
  parser.add_argument('mot_jde_dir')
  parser.add_argument('yolo_dir')

  args = parser.parse_args()
  main(args)
