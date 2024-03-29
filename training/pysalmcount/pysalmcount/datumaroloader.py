from .dataloader import DataLoader, Item
from ultralytics.utils.instance import Instances

import numpy as np
import cv2
import json
from pathlib import Path

class DatumaroLoader(DataLoader):
    DATUM_DIR = "datumaro_format"
    ANNO_DIR = "annotations"
    DEFAULT_JSON = 'default.json'
    KEY_ITEMS = 'items'
    KEY_PATH = 'path'
    KEY_IMAGE = 'image'
    KEY_ID = 'id'
    standard_names = [DATUM_DIR, ANNO_DIR, "default"]

    def __init__(self, root_folder, custom_classes: dict, file_list=None):
        path = Path(root_folder).resolve()
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory.")
        self.root_dir = path
        self.custom_classes = custom_classes

        if file_list is not None:
            self.clip_gen = self._gen_paths(file_list)
        else:
            self.clip_gen = self.root_dir.iterdir()
        self.file_list = file_list
            
        self.cur_clip = None
        self.cur_sub_clip_start_id = None
        self.num_items = None

    def _gen_paths(self, file_list):
        for path in file_list:
            yield Path(path)

    def _get_sub_clip_name(self, id=None):
        if id is not None:
            inp_id = id
        else:
            inp_id = self.cur_sub_clip_start_id
        clip_name = Path(self.datum_items[self.KEY_ITEMS][inp_id][self.KEY_ID]).parent
        return clip_name

    def _get_datum_dir(self):
        if (self._get_base_path() / self.DATUM_DIR).exists():
            return self.DATUM_DIR
        else:
            return ""
    
    def _get_images_path(self):
        return self._get_base_path() / self._get_datum_dir() / 'images' / self.standard_names[2]

    def _get_base_path(self):
        cur_clip = self.cur_clip
        while cur_clip.stem in self.standard_names:
            cur_clip = cur_clip.parent
        return cur_clip

    def _get_dirs(self, dir):
        for item in dir.iterdir():
            if item.is_dir():
                yield item
    
    def next_clip(self):
        if self.cur_sub_clip_start_id is not None:
            self.cur_sub_clip_start_id += self.num_items + 1
            clip_name = self._get_sub_clip_name()
        else:
            self.cur_clip = next(self.clip_gen)
            clip_name = self._get_base_path()
    
            # Read datumaro file
            if self.file_list is not None:
                datum_file = self.cur_clip
            else:
                datum_file = self.cur_clip / self._get_datum_dir() / self.ANNO_DIR / self.DEFAULT_JSON
            self.datum_items = self._json_loader(datum_file)

            try:
                # Test if this doesn't fail, then there are multiple clips in one datumaro file
                sub_name = self._get_sub_clip_name(0)
                if sub_name.resolve() == Path.cwd():
                    raise FileNotFoundError()
                    
                list(self._iter_subclip(sub_name, 0))
                        
                self.cur_sub_clip_start_id = 0
                clip_name = self._get_sub_clip_name()
            except IndexError:
                pass
            except FileNotFoundError:
                pass

        self.num_items = len(list(self._item_gen()))
        return clip_name

    def _iter_subclip(self, clip_name, start_id):
        i = 0
        it_clip_name = clip_name
        while clip_name == it_clip_name:
            yield self.datum_items[self.KEY_ITEMS][start_id + i]
            
            i += 1
            it_clip_name = self._get_sub_clip_name(start_id + i)

    def _item_gen(self):
        if self.cur_sub_clip_start_id is not None:
            clip_name = self._get_sub_clip_name()
            try:
                for item in self._iter_subclip(clip_name, self.cur_sub_clip_start_id):
                    yield item
            except IndexError:
                self.cur_sub_clip_start_id = None
        else:
            for datum_item in self.datum_items[self.KEY_ITEMS]:
                yield datum_item
    
    def items(self):
        if self.cur_clip is None:
            raise ValueError('No current clip')
            
        if self.num_items > 0:
            test_img = self.datum_items[self.KEY_ITEMS][0][self.KEY_IMAGE][self.KEY_PATH]
            if not Path(test_img).exists():
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
                    print(f"Error getting IDs from {self.cur_clip} | {datum_item['id']}:", e)
                    continue
                    
                box = np.concatenate((tmp_inst.bboxes[0], track_class))

                boxes = np.append(boxes, [box], axis=0) # Boxes() take in xyxy
                attrs.append(anno_attrs)
            # Populate each Item object
            path = datum_item[self.KEY_IMAGE][self.KEY_PATH]
            if not Path(path).exists():
                path = str(self._get_images_path() / path)
            item = Item(path, self.num_items, boxes, shape, attrs)
            yield item

    def fps(self):
        return 1
        
    def _json_loader(self, json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        return data

    def classes(self) -> dict:
        return self.custom_classes
