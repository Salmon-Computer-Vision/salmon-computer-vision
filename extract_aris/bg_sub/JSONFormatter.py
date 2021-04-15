from BgFrame import *

class JSONFormatter:
    def __init__(self):
        super().__init__()
        self.frames = []

    def get_frame(self, index):
        return self.frames[index]

    def add_frame(self, frame):
        self.frames.append(frame)
