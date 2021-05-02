import numpy as np
import cv2
from .BgUtility import *


class BackgroundSub:
    def __init__(self, frames, history, varThreshold, kernel_size, algorithm="MOG2", detectShadows=True):
        super().__init__()
        self.frames = frames
        self.algorithm = algorithm
        self.history = history
        self.varThreshold = varThreshold
        self.kernel_size = kernel_size
        self.detectShadows = detectShadows

    def subtract_background(self):
        bg_subtractor = self.__get_subtractor()
        bgSub_frames = []
        for index in range(len(self.frames)):
            frame = self.frames[index]
            frame = self.__blur_frame(frame, self.kernel_size)
            frame = bg_subtractor.apply(frame)
            frame = self.__do_morphological_operation(frame, self.kernel_size)
            frame = self.__convert_to_binary(frame)
            frame = BgUtility.convert_to_color_frame(frame)
            bgSub_frames.append(frame)
        return bgSub_frames

    def __blur_frame(self, frame, kernel_size):
        frame = cv2.blur(frame, (kernel_size, kernel_size))
        return frame

    def __convert_to_binary(self, frame):
        ret, thresh = cv2.threshold(frame, 0, 255, cv2.THRESH_OTSU)
        return thresh

    def __do_morphological_operation(self, frame, kernel_size):
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        frame = cv2.morphologyEx(frame, cv2.MORPH_CLOSE, kernel)
        frame = cv2.morphologyEx(frame, cv2.MORPH_OPEN, kernel)
        return frame

    def __get_subtractor(self):
        if self.algorithm == "MOG2":
            return cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.varThreshold,
                detectShadows=self.detectShadows
            )
        else:
            return cv2.createBackgroundSubtractorMOG2(
                history=self.history,
                varThreshold=self.varThreshold,
                detectShadows=self.detectShadows
            )
