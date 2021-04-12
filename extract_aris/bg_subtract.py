from bg_subtract import bgSub
from bg_object_label import bgObjLabel
from frame_extract import FrameExtract
from pyARIS import pyARIS
import os


def main():
    filename = "2020-05-27_071000.aris"
    file_path = get_file_path(filename)
    frame_start = 1775
    frame_end = 2782

    aris_data, frame = pyARIS.DataImport(file_path)
    frame_extract = FrameExtract(aris_data)
    frames = frame_extract.extract_frames(frame_start, frame_end, skipFrame=0)

    ### Background subtraction parameters
    history = 100
    varThreshold = 20
    kernel_size = 3
    bg_algorithm = "MOG2"
    detectShadows = True

    _bgSub = bgSub.BackgroundSub(
        frames, history, varThreshold, kernel_size, algorithm=bg_algorithm, detectShadows=detectShadows)
    bgSub_frame = _bgSub.subtract_background()

    objLabel = bgObjLabel.ObjectLabel(bgSub_frame.frames)
    bboxData = objLabel.label_objects()
    bboxData.export_data()

    objBgSubFrame = bgSub.BgSubtractFrames(objLabel.frames_bbox)
    objBgSubFrame.get_video("bg_sub_test.mp4")


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
