#!/bin/env python3
import cv2
import numpy as np

# Create a VideoCapture object and read from input file
# If the input is the camera, pass 0 instead of the video file name
cap = cv2.VideoCapture('rtsp://11.0.0.106/av0_0')

# Check if camera opened successfully
if (cap.isOpened()== False):
  print("Error opening video stream or file")


timme = strftime(f"%m-%d-%Y %H-%M-%S {suffix}", gmtime())
v_out = cv2.VideoWriter(

frame_id = 0
# Read until video is completed
while(cap.isOpened()):
  # Capture frame-by-frame
  ret, frame = cap.read()
  if ret == True:

    # Display the resulting frame
    #cv2.imshow('Frame',frame)
    cv2.imwrite('./save/{:05d}.jpg'.format(frame_id), frame)
    print(frame_id)

    # Press Q on keyboard to  exit
    #if cv2.waitKey(25) & 0xFF == ord('q'):
    #  break

    frame_id += 1
  # Break the loop
  else:
    break

# When everything done, release the video capture object
cap.release()

# Closes all the frames
cv2.destroyAllWindows()
