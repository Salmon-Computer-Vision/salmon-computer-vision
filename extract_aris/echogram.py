from pyARIS import pyARIS
from tqdm import tqdm
import numpy as np
from PIL import Image
import matplotlib.pyplot as plt
import cv2


source_file = '2020-05-27_071000.aris'


def get_echogram(aris_data, frame):
    num_frame = aris_data.FrameCount - 1
    echogram = np.array([])
    for i in tqdm(range(0, num_frame)):  # aris_data.FrameCount - 1
        _frame = pyARIS.FrameRead(aris_data, i)
        echogram = np.append(echogram, get_vertical_line(_frame))
    echogram = echogram.reshape(num_frame, frame.frame_data.shape[0])
    echogram = np.rot90(echogram)
    return echogram


def get_vertical_line(frame):
    vline = np.array([])
    for row in range(frame.frame_data.shape[0]):
        val = np.array(frame.frame_data[row]).max()
        vline = np.append(vline, val)
    return vline


def save_echogram_as_img(echogram, filename="my_echogram.png"):
    im = Image.fromarray(echogram).convert('RGB')
    im.save(filename)


def read_echogram_img(filename):
    im_frame = Image.open(filename).convert('L')
    return np.array(im_frame.getdata()).reshape(im_frame.size[1], im_frame.size[0])


def convolve_avg(frame):
    pass


if __name__ == '__main__':
    # aris_data, frame = pyARIS.DataImport(source_file)
    # echogram = get_echogram(aris_data, frame)
    # save_echogram_as_img(echogram)
    # plt.imshow(echogram, cmap='gray', vmin=0, vmax=255)
    # plt.show()

    echogram = read_echogram_img("my_echogram.png")
    plt.imshow(echogram, cmap='gray', vmin=0, vmax=255)
    plt.show()
