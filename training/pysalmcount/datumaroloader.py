from .dataloader import DataLoader, Item
from ultralytics.engine.results import Boxes

import json
from pathlib import Path

class DatumaroLoader(DataLoader):
    DATUM_PATH = Path('annotations') / 'default.json'

    def __init__(self, root_folder, custom_classes: dict):
        path = Path(root_folder).resolve()
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory.")
        self.root_dir = path
        self.custom_classes = custom_classes
        self.clip_gen = self.root_dir.iterdir()
        self.cur_clip = False
        
    def next_clip(self):
        self.cur_clip = next(self.clip_gen)
        return self.cur_clip
        
    def items(self):
        if not self.cur_clip:
            raise ValueError('No current clip')
        # Read datumaro file
        datum_items = self._json_loader(self.cur_clip / self.DATUM_PATH)
        num_items = len(datum_items['items'])
        # Iterate through items
        for datum_item in datum_items['items']:
            boxes = []
            attrs = []
            for anno in datum_item['annotations']:
                anno_attrs = anno['attributes']
                # Create Boxes with track ID and class
                boxes.append(Boxes(anno['bbox'] + [anno_attrs['track_id'], 1.0, anno['label_id']]))
                attrs.append(anno_attrs)
            # Populate each Item object
            item = Item(datum_item['image']['path'], num_items, boxes, attrs)
            yield item

    def _json_loader(self, json_file):
        with open(json_file, 'r') as f:
            data = json.load(f)
        return data

    def classes(self) -> dict:
        return self.custom_classes
