from .dataloader import DataLoader, Item

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
        return self.cur_clip

    def items(self):
        if not self.cur_clip:
            raise ValueError('Error: No current clip')

        cap = cv2.VideoCapture(self.cur_clip)
        if not cap.isOpened():
            raise VideoCaptureError(f"Error: Could not open video stream {self.cur_clip}.")

        self.fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            yield Item(frame, num_items=total_frames)

    def fps(self):
        return self.fps

    def classes(self) -> dict:
        """
        returns: Returns the custom classes dict. May return None if not initialized.
        """
        return self.custom_classes
