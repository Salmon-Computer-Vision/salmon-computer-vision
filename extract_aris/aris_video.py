#!/usr/bin/env python3

from pyARIS import pyARIS

def main():
  filename = "./2020-05-09_103000.aris"
  aris_data, frame = pyARIS.DataImport(filename)
  pyARIS.VideoExport(aris_data, 'test.mp4', start_frame=2650, end_frame=2720, vbr=13)

main()
