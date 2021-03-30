#!/usr/bin/env python
import sys
import os

def deserialize_anno(parts):
  # Frame name formatted as <task ID><6 digit frame ID>
  frame_name = parts[0]
  track_id = parts[1]
  x = float(parts[2])
  y = float(parts[3])
  box_width = float(parts[4])
  box_height = float(parts[5])
  class_id = parts[7]
  #print(frame_name, track_id, box_left, box_top, box_width, box_height, class_id)

  return frame_name, track_id, x, y, box_width, box_height, class_id
