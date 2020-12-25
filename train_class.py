def main():
  BATCH_SIZE = 32
  IMG_HEIGHT = 224
  IMG_WIDTH = 224

  train_ds = tf.keras.preprocessing.image_dataset_from_directory(
    str(data_root),
    validation_split=0.2,
    subset="training",
    seed=123,
    image_size=(img_height, img_width),
    batch_size=batch_size)

main()
