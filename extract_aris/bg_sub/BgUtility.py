import cv2
from .CocoAPI import CocoAPI


class BgUtility:
    def __init__(self):
        super().__init__()

    @staticmethod
    def export_video(frames, filename, invert_color=False):
        if invert_color:
            frames = BgUtility.__invert_color(frames)
        BgUtility.__get_video(frames, filename)

    @staticmethod
    def __invert_color(frames):
        for index in range(len(frames)):
            frames[index] = cv2.bitwise_not(frames[index])
        return frames

    @staticmethod
    def __get_video(frames, filename):
        height = frames[0].shape[0]
        width = frames[0].shape[1]
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        video = cv2.VideoWriter(filename, fourcc, 4.8, (width, height))
        for i in range(len(frames)):
            video.write(frames[i])
        video.release()
        cv2.destroyAllWindows()
