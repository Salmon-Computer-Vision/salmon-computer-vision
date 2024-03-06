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
    KEY_ID = 'id'
    standard_names = ["datumaro_format", "annotations", "default"]

    def __init__(self, root_folder, custom_classes: dict, file_list=None):
        path = Path(root_folder).resolve()
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory.")
        self.root_dir = path
        self.custom_classes = custom_classes

        if file_list:
            self.clip_gen = self._gen_paths(file_list)
            self.num_clips = len(file_list)
        else:
            self.clip_gen = self.root_dir.iterdir()
            self.num_clips = len(list(self.root_dir.iterdir()))
        self.file_list = file_list
            
        self.cur_clip = None
        self.cur_sub_clip_start_id = None

    def clips_len(self):
        return self.num_clips

    def _gen_paths(self, file_list):
        for path in file_list:
            yield Path(path)

    def _get_sub_clip_name(self, id=None):
        if id:
            inp_id = id
        else:
            inp_id = self.cur_sub_clip_start_id
        clip_name = Path(self.datum_items[self.KEY_ITEMS][inp_id][self.KEY_ID]).parent
        return clip_name

    def _get_images_path(self):
        return self._get_base_path() / self.standard_names[0] / 'images' / self.standard_names[2]

    def _get_base_path(self):
        cur_clip = self.cur_clip
        while cur_clip.stem in self.standard_names:
            cur_clip = cur_clip.parent
        return cur_clip
    
    def next_clip(self):
        if self.cur_sub_clip_start_id:
            self.cur_sub_clip_start_id += 1
            try:
                clip_name = self._get_sub_clip_name()
            except IndexError:
                self.cur_sub_clip_start_id = None
                return self.next_clip()
        else:
            self.cur_clip = next(self.clip_gen)
            clip_name = self._get_base_path()
    
            # Read datumaro file
            if self.file_list:
                datum_file = self.cur_clip
            else:
                datum_file = self.cur_clip / self.DATUM_PATH
            self.datum_items = self._json_loader(datum_file)

            # Check if there are multiple clips in one datumaro file
            if len(list(self._get_images_path().iterdir())) > 1:
                self.cur_sub_clip_start_id = 0
                clip_name = self._get_sub_clip_name()
        return clip_name

    def _item_gen(self):
        if self.cur_sub_clip_start_id:
            clip_name = self._get_sub_clip_name()
            i = 0
            while clip_name == self._get_sub_clip_name(i):
                yield self.datum_items[self.KEY_ITEMS][i]
                i += 1
        else:
            for datum_item in self.datum_items[self.KEY_ITEMS]:
                yield datum_item
    
    def items(self):
        if not self.cur_clip:
            raise ValueError('No current clip')
            
        num_items = len(list(self._item_gen()))
        if num_items > 0:
            test_img = self.datum_items[self.KEY_ITEMS][0][self.KEY_IMAGE][self.KEY_PATH]
            if self.file_list:
                test_img = str(self._get_images_path() / test_img)
            img = cv2.imread(test_img)
            h, w, _ = img.shape
            shape = (h, w)
            
        # Iterate through items
        for datum_item in self._item_gen():
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
                try:
                    track_class = np.asarray([int(anno_attrs['track_id']), 1.0, anno['label_id']])
                except KeyError as e:
                    print(f"Error getting IDs from {self.cur_clip} | {self.datum_item['id']}:", e)
                    continue
                    
                box = np.concatenate((tmp_inst.bboxes[0], track_class))

                boxes = np.append(boxes, [box], axis=0) # Boxes() take in xyxy
                attrs.append(anno_attrs)
            # Populate each Item object
            path = datum_item[self.KEY_IMAGE][self.KEY_PATH]
            if self.file_list:
                path = str(self._get_images_path() / path)
            item = Item(path, num_items, boxes, shape, attrs)
            yield item

    def fps(self):
        return 1
        
    def _json_loader(self, json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        return data

    def classes(self) -> dict:
        return self.custom_classes
