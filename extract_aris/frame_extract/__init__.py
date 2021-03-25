from pyARIS import pyARIS


class FrameExtract:
    def __init__(self, aris_data):
        super().__init__()
        self.aris_data = aris_data

    def extract_frames(self, frame_start, frame_end, skipFrame=24):
        frames = []
        for frame_index in range(frame_start, frame_end, skipFrame):
            frame = pyARIS.FrameRead(self.aris_data, frame_index)
            frames.append(frame.remap)
        return frames
