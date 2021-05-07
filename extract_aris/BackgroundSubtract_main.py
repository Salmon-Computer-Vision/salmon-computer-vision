from bg_sub.FrameExtract import *
from bg_sub.BgSubtract import *
from bg_sub.BgObjLabel import *
from bg_sub.BgFrame import BgFrame
from bg_sub.ObjectTracker import ObjectTracker
from bg_sub.BgUtility import BgUtility
from bg_sub.CocoAPI import CocoAPI
from pyARIS import pyARIS
import os


def get_file_path(filename):
    script_dir = os.path.dirname(__file__)
    abs_file_path = os.path.join(script_dir, filename)
    return abs_file_path


config = {
    "file_path": get_file_path("2020-05-27_071000.aris"),
    "frame_start": 1775,
    "frame_end": 2782,
    "history": 100,
    "varThreshold": 20,
    "kernel_size": 3,
    "bg_algorithm": "MOG2",
    "detectShadows": True,
    "object_tracker_radius": 5,
    "object_tracker_frame_threshold": 5,
}


def main():
    frames = extract_frames()
    bgSub_frames = subtract_background(frames)
    (objLabel, bboxData) = label_objects(bgSub_frames, exportData=True)

    start_tracker_and_export(bboxData, export_path="export")
    get_annotated_frames_from_coco(export_video=True)
    get_annotated_original_frames_from_coco(frames, export_video=True)
    export_bbox_result()
    export_sample_frames(frames, skip_frame=50)


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


def start_tracker_and_export(bboxData, export_path):
    bgFrames = convert_bboxData_to_bgFrames(bboxData)
    tracker = ObjectTracker(
        config["object_tracker_radius"],
        bgFrames,
        config["object_tracker_frame_threshold"]
    )
    json_formatter = tracker.start()
    json_formatter.export_json(export_path)


def get_annotated_frames_from_coco(export_video=False):
    coco_api = CocoAPI("export/object_coco.json", "export")
    annotated_images = coco_api.get_all_annotated_imgs(show_label=True)
    if export_video:
        BgUtility.export_video(
            annotated_images, "tracked_test.mp4", invert_color=False)
    return annotated_images


def get_annotated_original_frames_from_coco(frames, save_frames=False, export_video=False):
    coco_api = CocoAPI("export/object_coco.json", "export")
    save_frames_as_images(frames, "original_")
    annotated_original_images = coco_api.get_all_annotated_imgs(
        show_label=True, img_prefix="original_")
    if save_frames:
        save_frames_as_images(annotated_original_images, prefix="original_")
    if export_video:
        BgUtility.export_video(
            annotated_original_images, "tracked_original_test.mp4", invert_color=False)
    return annotated_original_images


def save_frames_as_images(frames, prefix=""):
    path = "export"
    for i in range(len(frames)):
        frame = frames[i]
        BgUtility.save_frame_as_image(
            frame, path, "{}.png".format(prefix + str(i)))


def export_bbox_result():
    coco_api = CocoAPI("export/object_coco.json", "export")
    coco_api.export_bbox_pred_result(skip_frame=50)


def export_sample_frames(frames, skip_frame=0):
    for i in range(0, len(frames), skip_frame + 1):
        BgUtility.save_frame_as_image(frames[i], "export/samples", "{}.png".format(i))


main()
