from .dataloader import DataLoader, Item
from ultralytics.utils.instance import Instances

import numpy as np
import cv2
import json
from pathlib import Path

class DatumaroLoader(DataLoader):
    DATUM_PATH = Path('annotations') / 'default.json'
    KEY_ITEMS = 'items'
    KEY_PATH = 'path'
    KEY_IMAGE = 'image'

    def __init__(self, root_folder, custom_classes: dict):
        path = Path(root_folder).resolve()
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory.")
        self.root_dir = path
        self.custom_classes = custom_classes
        self.clip_gen = self.root_dir.iterdir()
        self.num_clips = len(list(self.root_dir.iterdir()))
        self.cur_clip = False

    def clips_len(self):
        return self.num_clips
        
    def next_clip(self):
        self.cur_clip = next(self.clip_gen)
        return self.cur_clip
        
    def items(self):
        if not self.cur_clip:
            raise ValueError('No current clip')
        # Read datumaro file
        datum_items = self._json_loader(self.cur_clip / self.DATUM_PATH)
        num_items = len(datum_items[self.KEY_ITEMS])
        if num_items > 0:
            img = cv2.imread(datum_items[self.KEY_ITEMS][0][self.KEY_IMAGE][self.KEY_PATH])
            h, w, _ = img.shape
            shape = (h, w)
        # Iterate through items
        for datum_item in datum_items[self.KEY_ITEMS]:
            boxes = np.array([[]]).reshape((0,7)) # Box coords, track id, conf, and class id
            attrs = []
            for anno in datum_item['annotations']:
                anno_attrs = anno['attributes']
                # Create Boxes with track ID and class
                bbox = anno['bbox']
                # Set as x_center and y_center
                bbox[0] = bbox[0] + (bbox[2] / 2)
                bbox[1] = bbox[1] + (bbox[3] / 2)
                tmp_inst = Instances(np.asarray(bbox)) # Boxes are in xywh
                tmp_inst.convert_bbox('xyxy')
                track_class = np.asarray([anno_attrs['track_id'], 1.0, anno['label_id']])
                box = np.concatenate((tmp_inst.bboxes[0], track_class))

                boxes = np.append(boxes, [box], axis=0) # Boxes() take in xyxy
                attrs.append(anno_attrs)
            # Populate each Item object
            item = Item(datum_item[self.KEY_IMAGE][self.KEY_PATH], num_items, boxes, shape, attrs)
            yield item

    def _json_loader(self, json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        return data

    def classes(self) -> dict:
        return self.custom_classes
