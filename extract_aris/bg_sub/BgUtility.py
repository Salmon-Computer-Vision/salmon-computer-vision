import cv2
import os
import numpy as np
from PIL import Image


class BgUtility:
    def __init__(self):
        super().__init__()

    @staticmethod
    def export_video(frames, filename, invert_color=False, fps=4):
        if invert_color:
            frames = BgUtility.__invert_color(frames)
        BgUtility.__get_video(frames, filename, fps)

    @staticmethod
    def __invert_color(frames):
        for index in range(len(frames)):
            frames[index] = cv2.bitwise_not(frames[index])
        return frames

    @staticmethod
    def __get_video(frames, filename, fps):
        height = frames[0].shape[0]
        width = frames[0].shape[1]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(filename, fourcc, fps, (width, height))
        for i in range(len(frames)):
            frame = frames[i]
            if BgUtility.is_frame_gray(frame):
                frame = BgUtility.convert_to_color_frame(frame)
            video.write(frame)
        video.release()
        cv2.destroyAllWindows()

    @staticmethod
    def save_frame_as_image(frame, path, file_name):
        if BgUtility.is_frame_gray(frame):
            frame = BgUtility.convert_to_color_frame(frame)
        BgUtility.create_dir_if_not_exist(path)
        img = Image.fromarray(frame, "RGB")
        img.save("{}/{}".format(path, file_name))

    @staticmethod
    def is_frame_gray(frame):
        return len(frame.shape) == 2

    @staticmethod
    def convert_to_color_frame(frame):
        frame = np.stack((frame,)*3, axis=-1)
        return frame

    @staticmethod
    def create_dir_if_not_exist(name):
        if not os.path.exists(name):
            os.makedirs(name)
