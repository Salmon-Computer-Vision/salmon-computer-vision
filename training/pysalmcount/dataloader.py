from abc import ABC, abstractmethod
from ultralytics.engine.results import Boxes

class DataLoader(ABC):
    @abstractmethod
    def next_clip(self):
        pass
    
    @abstractmethod
    def items(self):
        pass

    @abstractmethod
    def classes(self) -> dict:
        ### Expects return format {0: class1, 1: class2, ...}
        pass

class Item():
    def __init__(self, frame, boxes: list[Boxes]=None, attributes: list[dict]=None):
        self.frame = frame # Can be image or path to file
        self.boxes = boxes
        self.attrs = attributes # Extra attributes if needed
