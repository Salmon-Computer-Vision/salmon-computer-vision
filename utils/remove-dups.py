#!/usr/bin/env python3

import fiftyone as fo
import sys

def main():
  if len(sys.argv) < 2:
    print(f"Usage: {sys.argv[0]} path/to/data_dir")
    return

  data_dir = sys.argv[1]
  #images_dir = sys.argv[2]

  dataset = fo.Dataset.from_dir(data_dir, 
      fo.types.CVATImageDataset)

  dataset.persistent = True

  print(dataset)
  print(dataset.head())

main()
