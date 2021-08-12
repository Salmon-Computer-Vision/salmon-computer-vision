#!/usr/bin/env python3
import sys
import glob, os
import argparse
import subprocess
import re

def main(args):
  result = subprocess.run([args.cli, '--auth', args.auth, '--server-host', args.host, 'ls'], stdout=subprocess.PIPE)
  print(re.search(r'967', result.stdout))
  #for vid in os.scandir(args.vid_folder):
  #  print(vid.path)
  return

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description='Creates new CVAT tasks for the videos at the share folder')

  parser.add_argument('--cli', default='../../cvat/utils/cli/cli.py', help='Path to cvat/utils/cli/cli.py')
  parser.add_argument('--host', default='localhost', help='Hostname of CVAT server. Default: localhost')
  parser.add_argument('auth', help='Username and password of CVAT instance. Should be passed as such "user:pass" or "user:$pass"')
  parser.add_argument('labels_path', help='Path to labels.json')
  parser.add_argument('share_folder', help='Path to CVAT share folder')
  parser.add_argument('vid_folder', help='Path to videos folder within the CVAT share folder')

  args = parser.parse_args()
  main(args)
