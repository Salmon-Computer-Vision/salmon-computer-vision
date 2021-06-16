import argparse
from pyARIS import pyARIS
from bg_sub.FrameExtract import FrameExtract
from bg_sub.BgUtility import BgUtility


def extract_frames(source_file, output_file, frame_start, frame_end, skip, fps, invert):
    aris_data, frame = pyARIS.DataImport(source_file)
    frame_start, frame_end = sanitize_frame_boundaries(frame_start, frame_end, aris_data)
    frames = FrameExtract(aris_data).extract_frames(frame_start, frame_end, skipFrame=skip)
    BgUtility.export_video(frames, output_file, invert_color=invert, fps=fps)


def sanitize_frame_boundaries(frame_start, frame_end, aris_data):
    if frame_start is None:
        frame_start = 0
    if frame_end is None:
        frame_end = aris_data.FrameCount - 1
    return frame_start, frame_end


def build_my_args(arguments):
    my_args = MyArgs()
    arg_dict = vars(arguments)
    for arg_name in arg_dict:
        arg_value = pack_arg(arg_dict[arg_name])
        setattr(my_args, arg_name, arg_value)
    return my_args


def pack_arg(arg):
    if arg is None:
        return None
    else:
        return extract_single_arg(arg)


def extract_single_arg(arg):
    if type(arg) is not list:
        return arg
    if len(arg) == 1:
        return arg[0]
    else:
        return arg


class MyArgs:
    def __init__(self):
        super().__init__()
        self.source_file = None
        self.output_file = None
        self.s = None
        self.e = None
        self.skip = None
        self.fps = None
        self.invert = None


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert ARIS file to videos.')

    parser.add_argument('source_file', nargs=1, type=str, help='path of the source ARIS file')
    parser.add_argument('output_file', nargs=1, type=str, help='path of the output video')
    parser.add_argument('-s', nargs=1, type=int, help='frame start')
    parser.add_argument('-e', nargs=1, type=int, help='frame end')
    parser.add_argument('--skip', nargs=1, type=int, help='skip frames for each exported frame', default=0)
    parser.add_argument('--fps', nargs=1, type=int, help='frames per second', default=24)
    parser.add_argument('--invert', nargs=1, type=bool, help='invert frame color', default=False)

    args = parser.parse_args()
    args = build_my_args(args)

    extract_frames(args.source_file, args.output_file, args.s, args.e, args.skip, args.fps, args.invert)
