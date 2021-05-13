import math
from .BgFrame import *
from .JSONFormatter import *


class ObjectTracker:
    def __init__(self, radius: int, frames: [BgFrame], frame_threshold: int, history: int):
        super().__init__()
        self.assignable_id = 0
        self.radius = radius
        self.history = history
        self.frames = frames
        self.json_formatter = JSONFormatter()
        self.json_formatter.add_category(0, "object", "")

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
            history_tracked_frames = self.__get_history_tracked_frames(i)
            updated_frame = self.__track_and_return_updated_frame(
                history_tracked_frames, self.frames[i])
            self.tracked_frames.append(updated_frame)

    def __get_history_tracked_frames(self, index):
        history_tracked_frames = []
        for i in range(self.history):
            history_index = index - i - 1
            if history_index < 0:
                break
            history_tracked_frames.insert(0, self.tracked_frames[history_index])
        return history_tracked_frames

    def __init_id(self, frame: BgFrame):
        bgObjects: [BgObject] = frame.get_all_objects()
        new_frame = BgFrame.clone_bgFrame_metadata(frame)
        for i in range(len(bgObjects)):
            bgObject = bgObjects[i]
            new_frame.create_and_add_object(
                self.__get_and_increment_assignable_id(), bgObject.get_xywh())
        return new_frame

    def __track_and_return_updated_frame(self, base_frames: [], updating_frame: BgFrame):
        updating_objects = updating_frame.get_all_objects()
        updated_frame = BgFrame.clone_bgFrame_metadata(updating_frame)
        updated_frame = self.__track_updating_objects(base_frames, updating_objects, updated_frame)
        return updated_frame

    def __track_updating_objects(self, base_frames: [], updating_objects: [], updated_frame: BgFrame):
        for updating_object in updating_objects:
            updated_frame = self.__compare_base_frames(base_frames, updating_object, updated_frame)
        return updated_frame

    def __compare_base_frames(self, base_frames: [], updating_object: BgObject, updated_frame: BgFrame):
        is_same = False
        for base_frame in base_frames:
            base_objects = base_frame.get_all_objects()
            updated_frame, is_same = self.__compare_base_objects(base_objects, updating_object, updated_frame)
            if is_same:
                break
        if not is_same:
            updated_frame.create_and_add_object(
                self.__get_and_increment_assignable_id(), updating_object.get_xywh())
        return updated_frame

    def __compare_base_objects(self, base_objects: [], updating_object: BgObject, updated_frame: BgFrame):
        is_same = False
        for base_object in base_objects:
            is_same, updated_frame = self.__compare_objects_and_update_frame(base_object, updating_object,
                                                                             updated_frame)
            if is_same:
                break
        return updated_frame, is_same

    def __compare_objects_and_update_frame(self, base_object: BgObject, updating_object: BgObject,
                                           updated_frame: BgFrame):
        if self.__is_same(base_object.get_xywh(), updating_object.get_xywh(), self.radius):
            updated_frame.create_and_add_object(
                base_object.get_id(), updating_object.get_xywh())
            is_same = True
            return is_same, updated_frame
        else:
            is_same = False
            return is_same, updated_frame

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
