#!/usr/bin/env python3
import yaml
from pathlib import Path
import argparse

from ultralytics import YOLO

from pysalmcount.datumaroloader import DatumaroLoader
from pysalmcount.videoloader import VideoLoader
from pysalmcount.salmon_counter import SalmonCounter

def main(args):
    with open('2023_combined_salmon.yaml', 'r') as file:
        data = yaml.safe_load(file)
        
    with open(args.anno_list_path, 'r') as f:
        anno_list = [line.strip() for line in f if line.strip()]

    if args.format == 'video':
        loader = VideoLoader(anno_list, data['names'])
    elif args.format == 'datumaro':
        loader = DatumaroLoader(args.input_directory, data['names'], anno_list)
    else:
        raise ValueError(f'Incorrect format: {args.format}')
    
    model = YOLO(args.weights)
    counter = SalmonCounter(model, loader, tracking_thresh=10)
    
    out_path = Path(args.csv_output_path)
    out_path.parent.mkdir(exist_ok=True)
    try:
        while True:
            try:
                counter.count(tracker='bytetrack.yaml', use_gt=False, save_vid=True, device=int(args.device))
            except StopIteration as e:
                raise
            except Exception as e:
                print(e)
                counter.salm_count.to_csv(args.csv_output_path)
    except StopIteration:
        print("Finish")
    counter.salm_count.to_csv(args.csv_output_path)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Generate counting stats for each video for the model on an input dataset.')
    parser.add_argument('input_directory', help='Root directory containing the desired test set.')
    parser.add_argument('anno_list_path', help='Filepath to a text file with a list of paths to the annotation file of each sequence.')
    parser.add_argument('csv_output_path', help='Output CSV filepath for saving the counts.')
    parser.add_argument('--weights', default='weights/best.pt', help='Path to YOLO weights to load.')
    parser.add_argument('--device', default=0, help='GPU device to use.')
    parser.add_argument('-f', '--format', default='datumaro', help='Input format. Acceptable formats: datumaro, video')
    args = parser.parse_args()

    main(args)
