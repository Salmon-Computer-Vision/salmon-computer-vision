#!/bin/env python3
import cv2
import numpy as np
from time import time, gmtime, strftime
import os

suffix = 'Coquitlam Dam'
interval = 3600 # In seconds
save_folder = 'save'

codec = cv2.VideoWriter_fourcc(*'mp4v')

cap = cv2.VideoCapture('rtsp://11.0.0.106/av0_0')

# Check if camera opened successfully
if (cap.isOpened()== False):
  print("Error opening video stream or file")


start = time()
timme = strftime("%m-%d-%Y %H-%M-%S", gmtime())
filename = os.path.join(save_folder, f"{timme} {suffix}")
v_out = cv2.VideoWriter(filename, codec, cap.get(cv2.CAP_PROP_FPS), 
    (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
print(f"Recording to {filename}")

# Read until video is completed
while(cap.isOpened()):
  # Capture frame-by-frame
  ret, frame = cap.read()
  if ret == True:

    # Display the resulting frame
    cv2.imshow('Frame',frame)

    now = time()
    if now - start > interval:
      start = now
      timme = strftime("%m-%d-%Y %H-%M-%S", gmtime())
      filename = os.path.join(save_folder, f"{timme} {suffix}")
      v_out.release()
      v_out = cv2.VideoWriter(filename, codec, cap.get(cv2.CAP_PROP_FPS), 
          (int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))))
      print(f"Recording to {filename}")

    v_out.write(frame)

    # Press Q on keyboard to  exit
    if cv2.waitKey(1) & 0xFF == ord('q'):
      break

  # Break the loop
  else:
    break

# When everything done, release the video capture object
cap.release()

# Closes all the frames
cv2.destroyAllWindows()
