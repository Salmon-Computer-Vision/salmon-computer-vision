import json
from .BgFrame import *


class JSONFormatter:
    def __init__(self):
        super().__init__()
        self.img_id = 0
        self.frames: [BgFrame] = []
        self.coco_format = {
            "images": [],
            "annotations": []
        }

    def get_frame(self, index) -> BgFrame:
        return self.frames[index]

    def add_frame(self, frame: BgFrame):
        self.frames.append(frame)

    def export_json(self):
        self.__frames_to_coco()
        with open("coco_json.txt", 'w') as outfile:
            json.dump(self.coco_format, outfile)

    def __frames_to_coco(self):
        for i in range(len(self.frames)):
            self.__parse_frame_to_coco(self.frames[i])

    def __parse_frame_to_coco(self, frame):
        self.coco_format["images"].append({
            "id": self.img_id,
            "width": 0,
            "height": 0,
            "file_name": frame.get_filename(),
            "license": 1,
        })

        bgObjects = frame.get_all_objects()
        for i in range(len(bgObjects)):
            bbox = []
            bgObject = bgObjects[i]
            xywh = bgObject.get_xywh()
            bbox.append(xywh["x"])
            bbox.append(xywh["y"])
            bbox.append(xywh["w"])
            bbox.append(xywh["h"])
            self.coco_format["annotations"].append({
                "id": bgObject.get_id(),
                "image_id": self.img_id,
                "category_id": 0,
                "bbox": [bbox]
            })
        self.img_id = self.img_id + 1
