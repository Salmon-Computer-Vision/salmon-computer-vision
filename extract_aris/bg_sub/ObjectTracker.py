import math
from .BgFrame import *
from .JSONFormatter import *


class ObjectTracker:
    def __init__(self, radius: int, frames: [BgFrame], frame_threshold: int):
        super().__init__()
        self.assignable_id = 0
        self.radius = radius
        self.frames = frames
        self.json_formatter = JSONFormatter()
        self.json_formatter.add_category(0, "salmon", "")

        self.frame_threshold = frame_threshold
        self.tracked_frames = []

    def start(self):
        self.__track_frames()
        self.__remove_noises()
        self.json_formatter.set_frames(self.tracked_frames)
        return self.json_formatter

    def __track_frames(self):
        first_frame = self.__init_id(self.frames[0])
        self.tracked_frames.append(first_frame)
        for i in range(1, len(self.frames)):
            updated_frame = self.__track_and_return_updated_frame(
                self.frames[i-1], self.frames[i])
            self.tracked_frames.append(updated_frame)

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

    def __remove_noises(self):
        counts = self.__count_objects_frequency()
        counts = self.__clean_counts_by_threshold(counts)
        self.__remove_frame_objects_by_threshold(counts)

    def __count_objects_frequency(self):
        counts = dict()
        for i in range(len(self.tracked_frames)):
            frame = self.tracked_frames[i]
            objects = frame.get_all_objects()
            for j in range(len(objects)):
                obj = objects[j]
                obj_id = obj.get_id()
                if obj_id in counts:
                    counts[obj_id] = counts[obj_id] + 1
                else:
                    counts[obj_id] = 1
        return counts

    def __clean_counts_by_threshold(self, counts):
        lower_than_threshold_keys = []
        for key in counts:
            if counts[key] < self.frame_threshold:
                lower_than_threshold_keys.append(key)
        for i in range(len(lower_than_threshold_keys)):
            del counts[lower_than_threshold_keys[i]]
        return counts

    def __remove_frame_objects_by_threshold(self, counts):
        for i in range(len(self.tracked_frames)):
            frame = self.tracked_frames[i]
            objects = frame.get_all_objects()

            for j in range(len(objects)):
                obj = objects[j]
                obj_id = obj.get_id()
                if obj_id not in counts:
                    frame.remove_object(obj_id)
