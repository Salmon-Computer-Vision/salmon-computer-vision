#!/usr/bin/env python3

import os
import subprocess

bashCommand = './create_task.sh'

def main():
  FOLDER = '/mnt/salmon-videos'

  name_path_dict = {} # Maps file names to their respective path locations
  for file_path, subdirs, filenames in os.walk(FOLDER):
    for filename in filenames:
      split_name = os.path.splitext(filename)
      name = split_name[0]
      ext = split_name[1]
      if ext in ['.m4v','.mp4','.mov']:
        full_path = os.path.join(file_path, filename)
        name_path_dict[name] = full_path
  #print(name_path_dict)

  count = 0
  for name in name_path_dict:
    #vid_path = name_path_dict[name]

    print(name)

    try:
      count = count + 1
    except ValueError:
      continue
  #print(count)

  return

main()
