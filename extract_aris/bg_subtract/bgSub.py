import numpy as np
import cv2


class BackgroundSub:
    def __init__(self, frames, algorithm="MOG2", history=100, varThreshold=50, detectShadows=True):
        super().__init__()
        self.frames = frames
        self.algorithm = algorithm
        self.history = history
        self.varThreshold = varThreshold
        self.detectShadows = detectShadows

    def subtract_background(self):
        bg_subtractor = self.__get_subtractor()
        bgSub_frames = []
        for index in range(len(self.frames)):
            img_2d = bg_subtractor.apply(self.frames[index])
            img_color_channel = self.__add_color_channel_to(img_2d)
            bgSub_frames.append(img_color_channel)
        return BgSubtractFrames(bgSub_frames)

    def __add_color_channel_to(self, img_2d):
        img_color_channel = np.stack((img_2d,)*3, axis=-1)
        return img_color_channel

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

    def get_video(self, file_name):
        height = self.frames[0].shape[0]
        width = self.frames[0].shape[1]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(file_name, fourcc, 24.0, (width, height))
        for i in range(len(self.frames)):
            video.write(self.frames[i])
        video.release()
        cv2.destroyAllWindows()
