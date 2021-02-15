#!/usr/bin/env python

import fiftyone as fo
import sys

def main():
  if len(sys.argv) < 3:
    return

  data_dir = sys.argv[1]
  images_dir = sys.argv[2]

  dataset = fo.Dataset.from_dir(data_dir, 
      fo.types.TFObjectDetectionDataset,
      images_dir=images_dir)

main()
