import math
from BgFrame import *
from JSONFormatter import *


class ObjectTracker:
    def __init__(self, frames: BgFrame, json_formatter: JSONFormatter):
        super().__init__()
        self.assignable_id = 0
        self.frames = frames
        self.json_formatter = json_formatter

    def track(self):
        self.__track_frames()

    def __track_frames(self):
        first_frame = self.__init_id(self.frames[0])
        self.json_formatter.add_frame(first_frame)
        for i in range(1, len(self.frames)):
            self.__track_frame(self.frames[i-1], self.frames[i])

    def __init_id(self, frame: BgFrame):
        bgObjects: [BgObject] = frame.get_all_objects()
        new_frame = BgFrame()
        for i in range(len(bgObjects)):
            bgObject = bgObjects[i]
            new_frame.create_and_add_object(
                self.__get_and_increment_assignable_id(), bgObject.get_xywh())
        return new_frame

    def __track_frame(self, frame1: BgFrame, frame2: BgFrame):
        pass

    def __is_same(self, xywh1, xywh2, radius):
        centroid1 = self.__calculate_centroid(xywh1)
        centroid2 = self.__calculate_centroid(xywh2)
        diff_x = centroid1[0] - centroid2[0]
        diff_y = centroid1[1] - centroid2[1]
        diff = (diff_x, diff_y)
        distance = math.sqrt(diff[0] ** 2 + diff[1] ** 2)
        return distance <= radius

    def __calculate_centroid(self, xywh):
        (x, y, w, h) = self.__unpack_xywh(xywh)
        centroid_x = w / 2 + x
        centroid_y = h / 2 + y
        return (centroid_x, centroid_y)

    def __unpack_xywh(self, xywh):
        x = xywh["x"]
        y = xywh["y"]
        w = xywh["w"]
        h = xywh["h"]
        return (x, y, w, h)

    def __get_and_increment_assignable_id(self):
        assignable_id = self.assignable_id
        self.__increment_id()
        return assignable_id

    def __increment_id(self):
        self.assignable_id = self.assignable_id + 1
