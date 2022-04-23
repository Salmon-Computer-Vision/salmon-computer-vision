from pyARIS import pyARIS
from tqdm import tqdm
import numpy as np
from PIL import Image
import pandas as pd
import cv2


source_file = '2020-05-27_071000.aris'
result_path = './result'


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


def echogram_to_img(echogram, filename="{}/echogram.png".format(result_path)):
    im = Image.fromarray(echogram).convert('RGB')
    im.save(filename)


def echogram_to_csv(echogram):
    pd.DataFrame(echogram).to_csv("{}/echogram.csv".format(result_path), index=False, header=False)


def csv_to_echogram(filename="{}/echogram.csv".format(result_path)):
    data = pd.read_csv(filename, header=None)
    return data.to_numpy()


def edge_detection(frame):
    kernel = np.array([[-1, -1, -1],
                    [-1, 8, -1],
                    [-1, -1, -1]])
    return cv2.filter2D(frame, -1, kernel)


def bg_sub(echogram):
    sub = cv2.createBackgroundSubtractorMOG2(
                history=100,
                varThreshold=20,
                detectShadows=False
            )

    # Iterate vertical lines on echogram
    bgsub_eg = np.array([])
    for col in range(echogram.shape[1]):
        bgsub_vline = sub.apply(echogram[:,col])
        bgsub_eg = np.append(bgsub_eg, bgsub_vline)
    bgsub_eg = bgsub_eg.reshape(echogram.shape[1], echogram.shape[0])
    bgsub_eg = np.rot90(bgsub_eg)
    return bgsub_eg


if __name__ == '__main__':
    aris_data, frame = pyARIS.DataImport(source_file)
    echogram = get_echogram(aris_data, frame)
    bgsub_eg = bg_sub(echogram)

    # Save echogram as image and as csv
    echogram_to_img(bgsub_eg)
    echogram_to_csv(bgsub_eg)

    bgsub_eg = csv_to_echogram()
