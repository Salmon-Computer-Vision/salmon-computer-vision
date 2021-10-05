#!/usr/bin/env python3

import argparse

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst
from gi.repository import Pipeline
Gst.init(None)


def main(args):
  def format_location_callback(splitmux, fragment_id):
    start = time.time()
    timme = time.strftime("%m-%d-%Y_%H-%M-%S", time.localtime())
    name = f"{timme}_{args.suffix}"
    return name

  pipeline = Gst.parse_launch("rtspsrc 'location=rtsp://192.168.10.98:554/user=admin&password=&channel=1&stream=0.sdp?' ! rtph265depay ! h265parse ! avdec_h265 ! v4l2convert ! 'video/x-raw, format=(string)BGR, width=(int)1280, height=(int)720' ! videorate ! 'video/x-raw,framerate=10/1' ! v4l2h264enc extra-controls="encode,video_bitrate=500000" ! h264parse ! mp4mux ! filesink location=test.mp4")

  pipeline.set_state(Gst.State.PLAYING)

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Record RTSP camera")
  parser.add_argument('-u', '--url', help='URL of RTSP stream.')
  parser.add_argument('-s', '--suffix', help='Suffix attached after the date of the video filename.')

  args = parser.parse_args()
  main(args)
