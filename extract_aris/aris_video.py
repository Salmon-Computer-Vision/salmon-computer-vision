#!/usr/bin/env python3

from pyARIS import pyARIS

def main():
  filename = "./2020-05-09_103000.aris"
  aris_data, frame = pyARIS.DataImport(filename)

main()
