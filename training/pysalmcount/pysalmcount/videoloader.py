from .dataloader import DataLoader, Item

import cv2

class VideoCaptureError(Exception):
    """Exception raised when video capture fails to open."""
    pass

class VideoLoader(DataLoader):
    def __init__(self, vid_sources, custom_classes=None):
        """
        vid_source: list[string] of anything that can go in VideoCapture() including video paths and RTSP URLs
        """
        self.vid_sources = vid_sources
        self.custom_classes = custom_classes
        self.num_clips = len(vid_sources)
        self.clip_gen = iter(vid_sources)
        self.cur_clip = None

    def clips_len(self):
        return self.num_clips

    def next_clip(self):
        self.cur_clip = next(self.clip_gen)

        self.cap = cv2.VideoCapture(self.cur_clip)
        if not self.cap.isOpened():
            raise VideoCaptureError(f"Error: Could not open video stream {self.cur_clip}.")

        self.vid_fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        return self.cur_clip

    def items(self):
        if not self.cur_clip:
            raise ValueError('Error: No current clip')

        while True:
            ret, frame = self.cap.read()
            if not ret:
                break

            yield Item(frame, num_items=self.total_frames)

    def fps(self):
        return self.vid_fps

    def classes(self) -> dict:
        """
        returns: Returns the custom classes dict. May return None if not initialized.
        """
        return self.custom_classes
