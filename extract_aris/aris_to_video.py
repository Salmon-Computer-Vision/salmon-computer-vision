import argparse
from pyARIS import pyARIS
from bg_sub.FrameExtract import FrameExtract
from bg_sub.BgUtility import BgUtility


def extract_frames(source_file, output_file, frame_start, frame_end, skip, fps, invert):
    aris_data, frame = pyARIS.DataImport(source_file)
    frame_extract = FrameExtract(aris_data)
    frames = frame_extract.extract_frames(
        frame_start, frame_end, skipFrame=skip)
    BgUtility.export_video(
        frames, output_file, invert_color=invert, fps=fps)


def pack_arguments(args):
    args_dict = vars(args)
    pack = dict()
    for arg_name in args_dict:
        pack[arg_name] = pack_arg(args_dict[arg_name])
    return pack


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


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Convert ARIS file to videos.')

    parser.add_argument('source_file', nargs=1, type=str, help='path of the source ARIS file')
    parser.add_argument('output_file', nargs=1, type=str, help='path of the output video')
    parser.add_argument('-s', nargs=1, type=int, help='frame start')
    parser.add_argument('-e', nargs=1, type=int, help='frame end')
    parser.add_argument('-skip', nargs=1, type=int, help='skip frames for each exported frame', default=0)
    parser.add_argument('-fps', nargs=1, type=int, help='frames per second', default=24)
    parser.add_argument('-invert', nargs=1, type=bool, help='frames per second', default=False)

    args = parser.parse_args()

    pack_args = pack_arguments(args)

    extract_frames(pack_args['source_file'], pack_args['output_file'], pack_args['s'], pack_args['e'],
                   pack_args['skip'], pack_args['fps'], pack_args['invert'])
