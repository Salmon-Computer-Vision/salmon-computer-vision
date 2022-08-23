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
      counts.append((line.rstrip(), []))

  print('Reading annotation files...')
  for anno_file in annos_paths:
    with open(anno_file, 'r') as f:
      for line in f:
        parts = line.strip().split(' ')
        class_id, track_id, *_ = deserialize_anno(parts)
        if not track_id in counts[class_id-1][1]:
          counts[class_id-1][1].append(track_id)

  print('Writing ground truth counts...')
  with open(args.output, 'w') as out:
    if not args.id:
      out.write('class,count\n')
    for i, categ in enumerate(counts):
      if args.id:
        out.write(f"{i+1},{len(categ[1])}\n")
      else:
        out.write(f"{categ[0]},{len(categ[1])}\n")
  print('Done.')

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Count ground truth classes')

  parser.add_argument('data_dir')
  parser.add_argument('-o', '--output', default='gt_counts.csv', help='Output CSV file. Default: gt_counts.csv')
  parser.add_argument('-i', '--id', action='store_true', help='Removes header and stores category names as IDs. Good for further scripts down the pipeline.')
  parser.set_defaults(func=count_jde)

  args = parser.parse_args()
  args.func(args)
