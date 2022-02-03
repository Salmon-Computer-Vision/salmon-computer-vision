#!/usr/bin/env python3
import sys
import glob, os
import argparse
import subprocess
import re
from time import sleep

def main(args):
  main_command = [args.cli, '--auth', args.auth, '--server-host', args.host]
  task_list = subprocess.run(main_command + ['ls'], stdout=subprocess.PIPE).stdout.decode('utf-8')
  for vid in os.scandir(args.vid_folder):
    filename = os.path.basename(vid.path)
    name = os.path.splitext(filename)[0]

    name_reg = re.compile(name)
    if re.search(name_reg, task_list):
      print(f"Task already exists. Skipping {name}")
      continue

    share_path = os.path.relpath(vid.path, args.share_folder)

    RETRY_LIMIT = 3
    count = 0
    while True:
      output = subprocess.run(main_command + ['create', '--labels', args.labels_path, name, 'share', share_path],
          stdout=subprocess.PIPE, stderr=subprocess.PIPE)
      create_out = output.stdout.decode('utf-8')
      create_err = output.stderr.decode('utf-8')
      print(create_out)
      if create_err:
        print(create_err)
      return create_out, create_err

      if count < RETRY_LIMIT and re.search(r'Error', create_err):
        count = count + 1
        task_id = re.search(r'ID: ([0-9]+)', create_out).group(1)
        subprocess.run(main_command + ['delete', task_id])
        sleep(3)
      else:
        break

    sleep(0.2)

  return

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Creates new CVAT tasks for the videos at the share folder')

  parser.add_argument('--cli', default='../../cvat/utils/cli/cli.py', help='Path to cvat/utils/cli/cli.py')
  parser.add_argument('--host', default='localhost', help='Hostname of CVAT server. Default: localhost')
  parser.add_argument('auth', help='Username and password of CVAT instance. Should be passed as such "user:pass" or "user:$pass" after `export pass=<pass>`')
  parser.add_argument('labels_path', help='Path to labels.json')
  parser.add_argument('share_folder', help='Path to CVAT share folder')
  parser.add_argument('vid_folder', help='Path to videos folder within the CVAT share folder')

  args = parser.parse_args()
  main(args)
