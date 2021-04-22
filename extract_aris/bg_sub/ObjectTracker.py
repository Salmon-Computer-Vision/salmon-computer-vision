import math
from .BgFrame import *
from .JSONFormatter import *


class ObjectTracker:
    def __init__(self, radius: int, frames: [BgFrame]):
        super().__init__()
        self.assignable_id = 0
        self.radius = radius
        self.frames = frames
        self.json_formatter = JSONFormatter()
        self.json_formatter.add_category(0, "salmon", "")

    def track(self):
        self.__track_frames()
        return self.json_formatter

    def __track_frames(self):
        first_frame = self.__init_id(self.frames[0])
        self.json_formatter.add_frame(first_frame)
        for i in range(1, len(self.frames)):
            updated_frame = self.__track_and_return_updated_frame(
                self.frames[i-1], self.frames[i])
            self.json_formatter.add_frame(updated_frame)

    def __init_id(self, frame: BgFrame):
        bgObjects: [BgObject] = frame.get_all_objects()
        new_frame = BgFrame.clone_bgFrame_metadata(frame)
        for i in range(len(bgObjects)):
            bgObject = bgObjects[i]
            new_frame.create_and_add_object(
                self.__get_and_increment_assignable_id(), bgObject.get_xywh())
        return new_frame

    def __track_and_return_updated_frame(self, base_frame: BgFrame, updating_frame: BgFrame):
        updated_frame = BgFrame.clone_bgFrame_metadata(updating_frame)
        base_objects = base_frame.get_all_objects()
        updating_objects = updating_frame.get_all_objects()
        for i in range(len(base_objects)):
            for j in range(len(updating_objects)):
                base = base_objects[i]
                updating = updating_objects[j]
                if self.__is_same(base.get_xywh(), updating.get_xywh(), self.radius):
                    updated_frame.create_and_add_object(
                        base.get_id(), updating.get_xywh())
                else:
                    updated_frame.create_and_add_object(
                        updating.get_id(), updating.get_xywh())
        return updated_frame

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
