from .dataloader import DataLoader, Item

from pathlib import Path

class ImageDirLoader(DataLoader):
    IMG_PATTERN = '*.[jpJP][npNP]*[gG$]'
    def __init__(self, root_folder, img_folder_name, custom_classes: dict):
        path = Path(root_folder).resolve()
        if not path.is_dir():
            raise ValueError(f"'{path}' is not a directory.")
        self.root_dir = path
        self.img_folder_name = img_folder_name
        self.custom_classes = custom_classes
        self.clip_gen = self.root_dir.iterdir()
        self.num_clips = len(list(self.root_dir.iterdir()))
        self.cur_clip = False

    def clips_len(self):
        return self.num_clips

    def next_clip(self):
        self.cur_clip = next(self.clip_gen)
        return self.cur_clip

    def items(self):
        if not self.cur_clip:
            raise ValueError('No current clip')
        frec = lambda p, g: sorted(p.glob(g))
        num_frames = len(list(frec(self.cur_clip / self.img_folder_name, self.IMG_PATTERN)))
        for f in frec(self.cur_clip / self.img_folder_name, self.IMG_PATTERN):
            item = Item(f, num_items=num_frames)
            yield item

    def classes(self) -> dict:
        return self.custom_classes