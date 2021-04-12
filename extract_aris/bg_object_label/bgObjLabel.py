import numpy as np
import cv2
import json
import os
from PIL import Image


class ObjectLabel:
    def __init__(self, frames):
        super().__init__()
        self.frames_gray = []
        self.frames_color = []
        self.frames_bbox = []
        self.stats = []

        [frames_color, frames_gray] = self.__preprocess_frames(frames)
        self.frames_color = frames_color
        self.frames_gray = frames_gray

    def __preprocess_frames(self, frames):
        if self.__get_frame_channel(frames[0]) == 1:
            frames_gray = frames
            frames_color = self.__convert_to_color(frames)
        else:
            frames_color = frames
            frames_gray = self.__convert_to_gray(frames)
        return [frames_color, frames_gray]

    def label_objects(self):
        for i in range(len(self.frames_gray)):
            output = cv2.connectedComponentsWithStats(
                self.frames_gray[i], 4, cv2.CV_32S)
            (numLabels, labels, stats, centroids) = output
            frame = self.frames_color[i].copy()
            for j in range(1, numLabels):
                xywh = self.__get_bbox_xywh(stats[j])
                frame = self.__draw_bbox(frame, xywh)
                frame = self.__draw_label(frame, str(j), xywh)
            self.frames_bbox.append(frame)
            self.stats.append(stats)
        return BBoxData(self.frames_color, self.stats)

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

    def get_bbox_on_frames(self, frames):
        [frames_color, frames_gray] = self.__preprocess_frames(frames)
        frames_bbox = []
        for i in range(len(self.stats)):
            frame = frames_color[i]
            stat = self.stats[i]
            for j in range(1, len(stat)):
                x = stat[j, cv2.CC_STAT_LEFT]
                y = stat[j, cv2.CC_STAT_TOP]
                w = stat[j, cv2.CC_STAT_WIDTH]
                h = stat[j, cv2.CC_STAT_HEIGHT]
                frame = np.ascontiguousarray(frame)
                frame = cv2.rectangle(
                    frame, (x, y), (x + w, y + h), (0, 255, 0), 3)

            frames_bbox.append(frame)
        return frames_bbox


class BBoxData:
    def __init__(self, frames, stats):
        super().__init__()
        self.frames = frames
        self.stats = stats
        self.dir_name = "export"
        self.img_ext = ".png"

    def export_data(self):
        if len(self.stats) == 0:
            raise NoBoundingBoxDataError()

        self.__create_dir_if_not_exist(self.dir_name)
        json_data = self.__create_default_json_data()
        for i in range(len(self.frames)):
            frame = self.frames[i]
            file_name = str(i) + self.img_ext
            export_path = self.__get_export_path(file_name)
            self.__save_frame_as_image(export_path, frame)
            default_frame_metadata = self.__create_default_frame_metadata()
            json_data["metadata"].append(default_frame_metadata)
            json_data["metadata"][i]["name"] = file_name
            for j in range(1, len(self.stats[i])):
                stat = self.stats[i][j]
                xywh = self.__get_xywh(stat)
                json_data["metadata"][i]["bounding_boxes"]["interested_objects"].append(
                    xywh)
        self.__write_data_to_file(json_data)

    def __create_dir_if_not_exist(self, name):
        if not os.path.exists(name):
            os.makedirs(name)

    def __create_default_json_data(self):
        json_data = {
            "metadata": []
        }
        return json_data

    def __get_export_path(self, file_name):
        return self.dir_name + "/" + file_name

    def __save_frame_as_image(self, file_name, frame):
        img = Image.fromarray(frame, "RGB")
        img.save(file_name)

    def __create_default_frame_metadata(self):
        metadata = {
            "name": "",
            "bounding_boxes": {
                "interested_objects": [],
                "noises": []
            }
        }
        return metadata

    def __get_xywh(self, stat):
        xywh = {}
        xywh["x"] = int(stat[cv2.CC_STAT_LEFT])
        xywh["y"] = int(stat[cv2.CC_STAT_TOP])
        xywh["w"] = int(stat[cv2.CC_STAT_WIDTH])
        xywh["h"] = int(stat[cv2.CC_STAT_HEIGHT])
        return xywh

    def __write_data_to_file(self, data):
        with open(self.dir_name + "/" + "json.txt", 'w') as outfile:
            json.dump(data, outfile)


class Error(Exception):
    def __init__(self, message):
        super().__init__(message)
        self.message = message


class NoBoundingBoxDataError(Error):
    def __init__(self):
        super().__init__("No bounding box data to export.")
