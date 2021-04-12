import numpy as np
import cv2


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
            frame = self.__add_color_channel_to(frame)
            bgSub_frames.append(frame)
        return BgSubtractFrames(bgSub_frames)

    def __blur_frame(self, frame, kernel_size):
        frame = cv2.blur(frame, (kernel_size, kernel_size))
        return frame

    def __convert_to_binary(self, frame):
        ret, thresh = cv2.threshold(frame, 0, 255, cv2.THRESH_OTSU)
        return thresh

    def __add_color_channel_to(self, img_2d):
        img_color_channel = np.stack((img_2d,)*3, axis=-1)
        return img_color_channel

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


class BgSubtractFrames:

    def __init__(self, frames):
        super().__init__()
        self.frames = frames

    def invert_color(self):
        for index in range(len(self.frames)):
            self.frames[index] = cv2.bitwise_not(self.frames[index])

    def get_video(self, file_name):
        height = self.frames[0].shape[0]
        width = self.frames[0].shape[1]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(file_name, fourcc, 4.8, (width, height))
        for i in range(len(self.frames)):
            video.write(self.frames[i])
        video.release()
        cv2.destroyAllWindows()
