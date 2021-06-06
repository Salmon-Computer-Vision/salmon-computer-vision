#!/usr/bin/env python
import argparse
import sys, glob, os

def deserialize_anno(parts):
  # {class_id} {track_id} {x_center / width} {y_center / height} {box_width / width} {box_height / height}
  class_id = int(parts[0])
  track_id = int(parts[1])
  x = float(parts[2])
  y = float(parts[3])
  box_width = float(parts[4])
  box_height = float(parts[5])

  return class_id, track_id, x, y, box_width, box_height

def count_jde(args):
  # Assuming JDE format to count ground truth classes
  data_dir = args.data_dir
  label_file = os.path.join(data_dir, 'gt', 'labels.txt')
  annos_loc = os.path.join(data_dir, 'labels_with_ids')
  annos_paths = glob.glob(os.path.join(annos_loc, "*"))

  counts = []
  with open(label_file, 'r') as f:
    for line in f:
      counts.append((line, []))

  for anno_file in annos_paths:
    with open(anno_file, 'r') as f:
      for line in f:
        parts = line.strip().split(',')
        class_id, track_id, *_ = deserialize_anno(parts)
        if not track_id in counts[class_id-1][1]:
          counts[class_id-1][1].append(track_id)

  with open('gt_counts.csv', 'w') as out:
    out.write('class,count\n')
    for categ in counts:
      out.write(f"{categ[0]}, {len(categ[1])}\n")

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Count ground truth classes')

  parser.add_argument('data_dir')
  parser.set_defaults(func=count_jde)

  args = parser.parse_args()
  args.func(args)
