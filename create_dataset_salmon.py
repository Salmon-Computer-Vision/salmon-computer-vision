#!/usr/bin/env python3

import cv2
import numpy as np
import pandas as pd
import os
import time
from datetime import datetime
import dateutil.parser as parser

H_TO_MS = 3.6e6
M_TO_MS = 6e4
S_TO_MS = 1000
MS_TO_MICRO = 1000
EPOCH = datetime.utcfromtimestamp(0)

EXTRACT_LENGTH = 3 # seconds of frame extraction

def time_to_ms(time: datetime.time):
  return time.hour * H_TO_MS + \
    time.minute * M_TO_MS + \
    time.second * S_TO_MS + \
    time.microsecond / MS_TO_MICRO

def name2date(name):
  return name.split(maxsplit=1)[0]

# Could raise ValueError exception if timestamp is badly formatted
def extract_frames(video_path, video_name, timeframe):
  t = datetime.strptime(timeframe, '%H:%M:%S').time()
  timestamp_milli = time_to_ms(t)
  DEST_FOLDER = 'frames'

  dest_dir = os.path.join(DEST_FOLDER, name2date(video_name))
  if not os.path.exists(dest_dir):
    os.makedirs(dest_dir)

  cap = cv2.VideoCapture(video_path)

  fps = cap.get(cv2.CAP_PROP_FPS)
  max_num_frames = round(fps * EXTRACT_LENGTH)

  # Seek timestamp in video
  cap.set(cv2.CAP_PROP_POS_MSEC, timestamp_milli)

  success, frame = cap.read()
  count = 1
  while success and count % max_num_frames != 0:
    filename = f"{video_name}-frame{count}.jpg"
    dest_path = os.path.join(dest_dir, filename)
    # TODO: downsample frame if necessary

    cv2.imwrite(dest_path, frame) # save frame as JPEG file
    print('Saved frame at', dest_path)
    count += 1

    success, frame = cap.read()

  cap.release()
  return

def main():
  FOLDER = '/home/sami/gdrive/Salmon Videos'

  name_path_dict = {} # Maps file names to their respective path locations
  for file_path, subdirs, filenames in os.walk(FOLDER):
    for name in filenames:
      full_path = os.path.join(file_path, name)
      name_path_dict[os.path.splitext(name)[0]] = full_path

  # Duplicate columns are added `.1`, `.2`, etc. at the end of the name
  # eg. Second "timeframe" column is "timeframe.1"
  df = pd.read_csv('Video_data.csv')

  df_one_fish = df[df.num_fish == 1]
  df_one_fish = df_one_fish.dropna(subset=['timeframe'])
  #print(len(df_one_fish.index))

  count = 0
  for i, entry in df_one_fish.iterrows():
    name = entry.video.strip()
    if name not in name_path_dict:
      #print(name)
      continue
    vid_path = name_path_dict[name]

    print(name)

    try:
      #extract_frames(vid_path, entry.video, entry.timeframe)
      count = count + 1
    except ValueError:
      continue
  #print(count)

  return

main()
