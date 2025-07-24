from abc import ABC, abstractmethod
import numpy as np

class DataLoader(ABC):
    @abstractmethod
    def next_clip(self):
        pass

    @abstractmethod
    def items(self):
        pass
    
    @abstractmethod
    def fps(self):
        pass

    @abstractmethod
    def classes(self) -> dict:
        ### Expects return format {0: class1, 1: class2, ...}
        pass

    @abstractmethod
    def close(self):
        pass

class Item():
    def __init__(self, frame, num_items, boxes=None, orig_shape=None,  attrs=None):
        """
        frame: Image frame or path to file
        num_items: int Number of items/frames
        boxes: numpy array with format (num_boxes, 7) with each row as [xyxy, track_id, conf, cls]
        orig_shape: The shape of the image frame
        attrs: Dictionary of extra attributes if needed
        """
        self.frame = frame
        self.num_items = num_items
        self.boxes = boxes # Per row: xyxy, track_id, conf, cls
        self.orig_shape = orig_shape
        self.attrs = attrs # Extra attributes if needed
