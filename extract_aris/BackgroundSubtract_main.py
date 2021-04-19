from bg_sub.FrameExtract import *
from bg_sub.BgSubtract import *
from bg_sub.BgObjLabel import *
from bg_sub.BgFrame import BgFrame
from bg_sub.ObjectTracker import ObjectTracker
from pyARIS import pyARIS
import os


def main():
    filename = "2020-05-27_071000.aris"
    file_path = get_file_path(filename)
    frame_start = 1775
    frame_end = 1800  # 2782

    aris_data, frame = pyARIS.DataImport(file_path)
    frame_extract = FrameExtract(aris_data)
    frames = frame_extract.extract_frames(frame_start, frame_end, skipFrame=0)

    # Background subtraction parameters
    history = 100
    varThreshold = 20
    kernel_size = 3
    bg_algorithm = "MOG2"
    detectShadows = True

    _bgSub = BackgroundSub(
        frames, history, varThreshold, kernel_size, algorithm=bg_algorithm, detectShadows=detectShadows)
    bgSub_frame = _bgSub.subtract_background()

    objLabel = ObjectLabel(bgSub_frame.frames)
    bboxData = objLabel.label_objects()
    bgFrames = convert_bboxData_to_bgFrames(bboxData)
    bboxData.export_data()

    tracker = ObjectTracker(5, bgFrames)
    tracker.track()

    objBgSubFrame = BgSubtractFrames(objLabel.frames_bbox)
    objBgSubFrame.get_video("bg_sub_test.mp4")

    original_bbox_frames = objLabel.get_bbox_on_frames(frames)
    originalBBoxFrames = BgSubtractFrames(original_bbox_frames)
    originalBBoxFrames.get_video("original_bbox_frames.mp4")


def convert_bboxData_to_bgFrames(bboxData: BBoxData):
    stats = bboxData.stats
    bgFrames = []
    for i in range(len(stats)):
        stat = stats[i]
        bgFrame = BgFrame.value_of(stat)
        bgFrames.append(bgFrame)
    return bgFrames


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
