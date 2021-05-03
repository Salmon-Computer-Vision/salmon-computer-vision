import json
from .BgFrame import *


class JSONFormatter:
    def __init__(self):
        super().__init__()
        self.img_id = 0
        self.ann_id = 0
        self.frames: [BgFrame] = []
        self.coco_format = {
            "images": [],
            "annotations": [],
            "categories": [],
        }

    def get_frame(self, index) -> BgFrame:
        return self.frames[index]

    def add_frame(self, frame: BgFrame):
        self.frames.append(frame)

    def set_frames(self, frames):
        self.frames = frames

    def add_category(self, cat_id, name, supercategory):
        self.coco_format["categories"].append(
            {
                "id": cat_id,
                "name": name,
                "supercategory": supercategory,
            }
        )

    def export_json(self, path):
        self.__frames_to_coco()
        with open("{}/object_coco.json".format(path), 'w') as outfile:
            json.dump(self.coco_format, outfile)

    def __frames_to_coco(self):
        for i in range(len(self.frames)):
            self.__parse_frame_to_coco(self.frames[i])

    def __parse_frame_to_coco(self, frame):
        self.coco_format["images"].append({
            "id": self.img_id,
            "width": frame.metadata["width"],
            "height": frame.metadata["height"],
            "file_name": frame.metadata["filename"],
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
                "id": self.__get_and_increment_ann_id(),
                "object_id": bgObject.get_id(),
                "image_id": self.img_id,
                "category_id": 0,
                "bbox": bbox,
                "segmentation": [],
            })
        self.img_id = self.img_id + 1
    
    def __get_and_increment_ann_id(self):
        ann_id = self.ann_id
        self.ann_id = self.ann_id + 1
        return ann_id
