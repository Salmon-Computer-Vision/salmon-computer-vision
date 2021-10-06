#!/usr/bin/env python3
import os
import signal
import sys
import argparse
import time

import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
Gst.init(None)

os.environ["GST_DEBUG"] = '4'

vid_interval = int(3.6e12) # In nanoseconds
#vid_interval = int(1.2e10) # In nanoseconds


def main(args):
  def format_location_callback(splitmux, fragment_id):
    start = time.time()
    timme = time.strftime("%m-%d-%Y_%H-%M-%S", time.localtime())
    name = f"{timme}_{args.suffix}"
    return name

  pipeline = Gst.parse_launch(f"rtspsrc location=rtsp://192.168.10.98:554/user=admin&password=&channel=1&stream=0.sdp? ! rtph265depay ! h265parse ! avdec_h265 ! v4l2convert ! video/x-raw, format=(string)BGR, width=(int)1280, height=(int)720 ! videorate ! video/x-raw,framerate=10/1 ! v4l2h264enc extra-controls=encode,video_bitrate=500000 ! queue ! h264parse ! splitmuxsink location=test%d.mp4 max-size-time={vid_interval}")

  pipeline.set_state(Gst.State.PLAYING)

  def signal_handler(sig, frame):
    print("Shutting down pipeline...")
    pipeline.send_event(Gst.Event.new_eos())


  signal.signal(signal.SIGINT, signal_handler)
  loop = GLib.MainLoop()

  def on_message(bus: Gst.Bus, message: Gst.Message, loop_thr: GLib.MainLoop):
    mtype = message.type
    if mtype == Gst.MessageType.EOS:
      pipeline.set_state(Gst.State.NULL)
      pipeline.get_state(5) # Will wait for state to change for 5 seconds
      sys.exit(0)

  bus = pipeline.get_bus()
  bus.connect("message", on_message, None)
  bus.add_signal_watch()

  try:
    loop.run()
  except:
    loop.quit()

if __name__ == '__main__':
  parser = argparse.ArgumentParser(description="Record RTSP camera. Can record multiple at once.")
  parser.add_argument('-u', '--url', action='append', help='URL of RTSP stream. Supply multiple options to record more than one.')
  parser.add_argument('-s', '--suffix', action='append', help='Suffix attached after the date of the video filename.')

  args = parser.parse_args()
  if len(args.url) != len(args.suffix):
    print("Number of URLs and Suffixes must match.")
    sys.exit(1)
  main(args)
