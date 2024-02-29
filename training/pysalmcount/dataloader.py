from abc import ABC, abstractmethod
import numpy as np

class DataLoader(ABC):
    @abstractmethod
    def next_clip(self):
        pass

    @abstractmethod
    def clips_len(self):
        pass

    @abstractmethod
    def items(self):
        pass

    @abstractmethod
    def classes(self) -> dict:
        ### Expects return format {0: class1, 1: class2, ...}
        pass

class Item():
    def __init__(self, frame, num_items: int, boxes: np.array=None, orig_shape=None,  attrs: list[dict]=None):
        self.frame = frame # Can be image or path to file
        self.num_items = num_items
        self.boxes = boxes # Per row: xyxy, track_id, conf, cls
        self.orig_shape = orig_shape
        self.attrs = attrs # Extra attributes if needed
