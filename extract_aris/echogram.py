from pyARIS import pyARIS
from tqdm import tqdm
import numpy as np
import matplotlib.pyplot as plt


source_file = '2020-05-27_071000.aris'


def get_echogram(aris_data):
    # num_frame = aris_data.FrameCount - 1
    num_frame = 50
    echogram = np.array([])
    for i in tqdm(range(0, num_frame)):  # aris_data.FrameCount - 1
        _frame = pyARIS.FrameRead(aris_data, i)
        echogram = np.append(echogram, get_vertical_line(_frame))
    echogram = echogram.reshape(frame.frame_data.shape[0], num_frame)
    return echogram


def get_vertical_line(frame):
    vline = np.array([])
    for row in range(frame.frame_data.shape[0]):
        val = np.array(frame.frame_data[row]).mean()
        vline = np.append(vline, val)
    return vline


if __name__ == '__main__':
    aris_data, frame = pyARIS.DataImport(source_file)
    echogram = get_echogram(aris_data)
    plt.imshow(echogram, cmap='gray', vmin=0, vmax=255)
    plt.show()
