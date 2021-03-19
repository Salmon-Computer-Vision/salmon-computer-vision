import numpy as np
import cv2


class ObjectLabel:
    def __init__(self, frames):
        super().__init__()
        self.frames_gray = []
        self.frames_color = []
        self.frames_bbox = []
        self.stats = []

        if self.__get_frame_channel(frames[0]) == 1:
            self.frames_gray = frames
            self.frames_color = self.__convert_to_color(frames)
        else:
            self.frames_color = frames
            self.frames_gray = self.__convert_to_gray(frames)

    def label_objects(self):
        for i in range(len(self.frames_gray)):
            output = cv2.connectedComponentsWithStats(
                self.frames_gray[i], 4, cv2.CV_32S)
            (numLabels, labels, stats, centroids) = output
            frame = self.frames_color[i]
            for j in range(1, numLabels):
                xywh = self.__get_bbox_xywh(stats[j])
                frame = self.__draw_bbox(frame, xywh)
                frame = self.__draw_label(frame, str(j), xywh)
            self.frames_bbox.append(frame)
            self.stats.append(stats)

    def get_stats(self):
        return self.stats

    def __convert_to_gray(self, frames):
        gray_frames = []
        for i in range(len(frames)):
            gray_frame = cv2.cvtColor(frames[i], cv2.COLOR_BGR2GRAY)
            gray_frames.append(gray_frame)
        return gray_frames

    def __convert_to_color(self, frames):
        color_frames = []
        for i in range(len(frames)):
            color_frame = self.__add_color_channel_to(frames[i])
            color_frames.append(color_frame)
        return color_frames

    def __get_bbox_xywh(self, stat):
        xywh = {}
        xywh['x'] = stat[cv2.CC_STAT_LEFT]
        xywh['y'] = stat[cv2.CC_STAT_TOP]
        xywh['w'] = stat[cv2.CC_STAT_WIDTH]
        xywh['h'] = stat[cv2.CC_STAT_HEIGHT]
        return xywh

    def __draw_bbox(self, frame, xywh, color=(0, 255, 0), thickness=1):
        x = xywh['x']
        y = xywh['y']
        width = xywh['w']
        height = xywh['h']
        _frame = cv2.rectangle(
            frame, (x, y), (x + width, y + height), color, thickness)
        return _frame

    def __draw_label(self, frame, label, xywh, color=(0, 255, 0), thickness=1):
        frame = cv2.putText(
            frame, label, (xywh['x'], xywh['y'] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, thickness)
        return frame

    def __get_frame_channel(self, frame):
        if (len(frame.shape) == 2):
            return 1
        else:
            return frame.shape[2]

    def __add_color_channel_to(self, frame):
        img_color_channel = np.stack((frame,)*3, axis=-1)
        return img_color_channel
