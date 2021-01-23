#!/usr/bin/env python3

import numpy as np
import time

#import PIL.Image as Image
#import matplotlib.pylab as plt

import tensorflow as tf
#import tensorflow_hub as hub

def main():
  DATA_PATH = "test/images"
  BATCH_SIZE = 32
  IMG_HEIGHT = 224
  IMG_WIDTH = 224

  #print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))

#  train_ds = tf.keras.preprocessing.image_dataset_from_directory(
#    DATA_PATH,
#    validation_split=0.2,
#    subset="training",
#    seed=123,
#    image_size=(IMG_HEIGHT, IMG_WIDTH),
#    batch_size=BATCH_SIZE)

  #print(train_ds)

  filename = './anno/test right bank-tf_detection_api/default.tfrecord'
  raw_dataset = tf.data.TFRecordDataset(filename)

  print(raw_dataset);

  example = tf.train.Example()
  for raw_record in raw_dataset.enumerate(0).take(65):
    if raw_record[0] >= 63:
      example.ParseFromString(raw_record[1].numpy())
      print(example.features.feature)

main()
