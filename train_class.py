#!/usr/bin/env python3

import numpy as np
import time

import PIL.Image as Image
import matplotlib.pylab as plt

import tensorflow as tf
import tensorflow_hub as hub

def main():
  DATA_PATH = "/home/sami/gdrive/Salmon Videos/image_dataset/frames/09-23-2019"
  BATCH_SIZE = 32
  IMG_HEIGHT = 224
  IMG_WIDTH = 224

  print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))

  train_ds = tf.keras.preprocessing.image_dataset_from_directory(
    DATA_PATH,
    validation_split=0.2,
    subset="training",
    seed=123,
    image_size=(img_height, img_width),
    batch_size=batch_size)

main()
