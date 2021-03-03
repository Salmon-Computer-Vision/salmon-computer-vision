from bg_subtract import bgSub
from pyARIS import pyARIS
import os


def main():
    filename = "2020-05-27_071000.aris"
    file_path = get_file_path(filename)
    frame_start = 1775
    frame_end = 2782

    aris_data, frame = pyARIS.DataImport(file_path)
    frames = extract_frames(aris_data, frame_start, frame_end)

    history = 100
    varThreshold = 60
    detectShadows = True

    _bgSub = bgSub.BackgroundSub(frames, history=history, varThreshold=varThreshold, detectShadows=detectShadows)
    bgSub_frame = _bgSub.subtract_background()
    bgSub_frame.get_video("bg_sub_test.mp4")


def get_file_path(filename):
    script_dir = os.path.dirname(__file__)
    abs_file_path = os.path.join(script_dir, filename)
    return abs_file_path


def extract_frames(aris_data, frame_start, frame_end):
    frames = []
    for frame_index in range(frame_start, frame_end + 1):
        frame = pyARIS.FrameRead(aris_data, frame_index)
        frames.append(frame.remap)
    return frames


main()
