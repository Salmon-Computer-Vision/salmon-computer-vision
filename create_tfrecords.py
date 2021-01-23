#!/usr/bin/env python3

import tensorflow as tf

def append_records_v2(in_file, out_file):
  with tf.io.TFRecordWriter(out_file) as writer:
    ds = tf.data.TFRecordDataset([in_file])
    for rec in ds:
      print(rec.numpy()[0])
      writer.write(rec.numpy())
      return

def main():
  filename = './anno/test right bank-tf_detection_api/default.tfrecord'
  out = 'test.tfrecord'
  append_records_v2(filename, out)

main()
