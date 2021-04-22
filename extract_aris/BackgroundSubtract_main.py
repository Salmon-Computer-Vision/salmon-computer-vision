from bg_sub.FrameExtract import *
from bg_sub.BgSubtract import *
from bg_sub.BgObjLabel import *
from bg_sub.BgFrame import BgFrame
from bg_sub.ObjectTracker import ObjectTracker
from bg_sub.BgUtility import BgUtility
from pyARIS import pyARIS
import os


def get_file_path(filename):
    script_dir = os.path.dirname(__file__)
    abs_file_path = os.path.join(script_dir, filename)
    return abs_file_path


config = {
    "file_path": get_file_path("2020-05-27_071000.aris"),
    "frame_start": 1775,
    "frame_end": 1800,  # 2782
    "history": 100,
    "varThreshold": 20,
    "kernel_size": 3,
    "bg_algorithm": "MOG2",
    "detectShadows": True
}


def main():
    frames = extract_frames()
    bgSub_frames = subtract_background(frames)
    (objLabel, bboxData) = label_objects(bgSub_frames, exportData=False)
    bgFrames = convert_bboxData_to_bgFrames(bboxData)

    # bboxData.export_data()

    tracker = ObjectTracker(5, bgFrames)
    json_formatter = tracker.track()
    json_formatter.export_json()

    # BgUtility.export_video(objLabel.frames_bbox,
    #                        "bg_sub_test.mp4", invert_color=False)

    # BgUtility.export_video(objLabel.get_bbox_on_frames(frames),
    #                        "original_bbox_frames.mp4", invert_color=False)


def extract_frames():
    aris_data, frame = pyARIS.DataImport(config["file_path"])
    frame_extract = FrameExtract(aris_data)
    frames = frame_extract.extract_frames(
        config["frame_start"], config["frame_end"], skipFrame=0)
    return frames


def subtract_background(frames):
    _bgSub = BackgroundSub(
        frames,
        config["history"],
        config["varThreshold"],
        config["kernel_size"],
        algorithm=config["bg_algorithm"],
        detectShadows=config["detectShadows"]
    )
    bgSub_frame = _bgSub.subtract_background()
    return bgSub_frame


def label_objects(frames, exportData=False):
    objLabel = ObjectLabel(frames)
    bboxData = objLabel.label_objects()
    if exportData:
        bboxData.export_data()
    return (objLabel, bboxData)


def convert_bboxData_to_bgFrames(bboxData: BBoxData):
    stats = bboxData.stats
    bgFrames = []
    for i in range(len(stats)):
        stat = stats[i]
        bgFrame = BgFrame.of(
            stat, 
            "{}.png".format(i), 
            bboxData.width, 
            bboxData.height
        )
        bgFrames.append(bgFrame)
    return bgFrames


main()
