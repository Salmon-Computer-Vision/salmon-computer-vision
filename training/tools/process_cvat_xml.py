#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
import concurrent.futures
from threading import Lock
from datumaro.components.dataset import Dataset
import argparse
import yaml
from pathlib import Path
import pandas as pd
import time

DUP_LABELS_MAPPING = {
        'White Fish': 'Whitefish',
        'Bull Trout': 'Bull',
        'Lan prey': 'Lamprey',
        'Lampray': 'Lamprey',
        'Coho Salmon': 'Coho',
        'Rainbow Trout': 'Rainbow',
        'Sockeye Salmon': 'Sockeye',
        'Pink Salmon': 'Pink',
        'Chinook Salmon': 'Chinook',
        'Chum Salmon': 'Chum',
        'Cutthroat Trout': 'Cutthroat',
        'Dolly Varden': 'Bull',
        }

CVAT_FORMAT = 'cvat'
DATUM_FORMAT = 'datumaro'
standard_names = ['datumaro_format', 'annotations', "default", "output"]

def write_error(file_path):
    with write_datum_lock: # Safely write to error output files
        with open(error_output_file_path, 'a') as f:
            f.write(file_path + '\n')
            
def process_dataset(dataset_path, output_base_dir, no_filter=False, format=CVAT_FORMAT, out_format=DATUM_FORMAT, save_media=False, empty_only=False, num_empty=None):
    # Process a single XML file: rename '__instance_id' to 'track_id', convert to Datumaro format and export.
    relative_path = os.path.relpath(dataset_path, start=original_root_dir)
    new_path = os.path.join(output_base_dir, relative_path)
    os.makedirs(new_path, exist_ok=True)
    output_dir = os.path.join(new_path, f'{out_format}_format')
    
    import_path = new_path if format == CVAT_FORMAT else dataset_path

    if out_format == DATUM_FORMAT:
        output_anno = os.path.join(output_dir, 'annotations', 'default.json')
        output_empty = os.path.join(output_dir, 'annotations', 'empty')
        if os.path.exists(output_anno):
            print(f"Exists skipping... {output_anno}")
            return
        elif os.path.exists(output_empty):
            print(f"Empty exists skipping... {output_empty}")
            return
    elif out_format == 'yolo':
        output_data = os.path.join(output_dir, 'obj.data')
        if os.path.exists(output_data):
            print(f"Exists skipping... {output_data}")
            return
    else:
        if os.path.exists(output_dir):
            print(f"Exists skipping... {output_dir}")
            return
        
    try:
        if format == CVAT_FORMAT:
            # Load and Transform CVAT XML
            tree = ET.parse(os.path.join(dataset_path, 'output.xml'))
            root = tree.getroot()
    
            # Find the attribute with name "__instance_id" and rename it to "track_id"
            for elem in root.iter('attribute'):
                if elem.get('name') == '__instance_id':
                    elem.set('name', 'track_id')
                
            # Save the modified XML to a new file in the new output directory
            tree.write(os.path.join(new_path, 'output.xml'))

        # Convert to Datumaro format and export
        with write_datum_lock:
            dataset = Dataset.import_from(import_path, format=format)
        dataset = dataset.transform('remap_labels', mapping=DUP_LABELS_MAPPING)
        dataset = dataset.transform('project_labels', dst_labels=LABELS_ORDER)
        if not no_filter and not empty_only:
            dataset = dataset.filter('/item/annotation') # Must filter after remapping due to removed annotations
        elif empty_only:
            dataset = dataset.filter('/item[not(annotation)]')
            if num_empty is not None:
                dataset = dataset.transform('random_sampler', count=num_empty, seed=40)
            
        try:
            dataset = dataset.transform('map_subsets', mapping={'output': 'default'})
        except Exception as e:
            print(f'Failed to map subset "output" to "default" likely no "output" subset: {e}')

        dataset.export(output_dir, format=out_format, save_media=save_media)
        
        if out_format == DATUM_FORMAT:
            if not os.path.exists(output_anno):
                with open(output_empty, 'w') as f:
                    f.write('empty\n')
        
    except ET.ParseError as e:
        print(f"Parse error processing dataset {dataset_path}: {e}")
        write_error(dataset_path)
    except Exception as e:
        print(f"Error processing dataset {dataset_path}: {e}")
        write_error(dataset_path)

def find_xml_files(root_dir):
    # Recursively search for all 'output.xml' files within a given directory.
    for subdir, dirs, files in os.walk(root_dir):
        for filename in files:
            if filename == 'output.xml':
                yield subdir

def get_seq_path(path):
    seq_name = path
    while seq_name.stem in standard_names:
        seq_name = seq_name.parent
    return seq_name

def find_set_files(root_dir, set_names, anno_name):
    for file_path in Path(root_dir).rglob(anno_name):
        seq_path = get_seq_path(file_path)
        if seq_path.name in set_names:
            yield str(seq_path)

def list_datasets(root_dir):
    for name in os.listdir(root_dir):
        yield os.path.join(root_dir, name)

def main(args):
    # Main function to process all 'output.xml' files found in the given directory.
    global original_root_dir
    global error_output_file_path
    global write_datum_lock
    global LABELS_ORDER
    write_datum_lock = Lock()
    original_root_dir = args.input_directory
    error_output_file_path = os.path.join(args.output_directory, 'error_files.txt')
    
    with open(args.labels_file, 'r') as file:
        data = yaml.safe_load(file)
    LABELS_ORDER = list(data['names'].values())

    if args.format == CVAT_FORMAT and args.set_file is None:
        datasets = list(find_xml_files(args.input_directory))
    elif args.set_file is not None:
        df_set = pd.read_csv(args.set_file, index_col=0)
        set_names = df_set.index

        datasets = list(find_set_files(args.input_directory, set_names, args.anno_name))

        # Error handling
        extracted_filenames = [Path(d).name for d in datasets]
        difference = set(set_names) - set(extracted_filenames)
        # Write the difference to a text file
        output_file = 'difference.txt'
        if len(difference) > 0:
            with open(output_file, 'w') as f:
                for filename in difference:
                    f.write(f"{filename}\n")
            print(f"Error: missing data in input folder. The missing filenames are outputted in {output_file}")
    else:
        datasets = list(list_datasets(args.input_directory))

    # Process each file in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Create a partial function call including the output base directory
        from functools import partial
        process_file = partial(process_dataset, output_base_dir=args.output_directory, 
                               no_filter=args.no_filter, format=args.format, out_format=args.out_format,
                               save_media=args.save_media, empty_only=args.empty_only, num_empty=args.num_empty)
        executor.map(process_file, datasets)

# Command-line interface setup
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process CVAT XML files in parallel and convert them to Datumaro format.')
    parser.add_argument('input_directory', help='Root directory containing the CVAT XML files')
    parser.add_argument('output_directory', help='Root directory for saving the processed files and Datumaro datasets')
    parser.add_argument('labels_file', help='Path to labels file in YOLOv8 YAML format')
    parser.add_argument('--workers', type=int, default=None,
                        help='Maximum number of threads to use. Defaults to the number of CPU cores if not set.')
    parser.add_argument('--no-filter', action='store_true',
                        help='Turn off filtering of only items that have annotations')
    parser.add_argument('--set-file', default=None,
                        help='Path to CSV file storing the filenames in the FIRST column for a particular set. Will filter to only these data.')
    parser.add_argument('--anno-name', default='default.json',
                        help='Annotation name to search with set file')
    parser.add_argument('-f', '--format', default=CVAT_FORMAT,
                        help='Input format of annotations for Datumaro to import')
    parser.add_argument('-o', '--out-format', default=DATUM_FORMAT,
                        help='Output format of annotations based on what Datumaro can export')
    parser.add_argument('--save-media', action='store_true',
                        help='Save media in output folder')
    parser.add_argument('--empty-only', action='store_true',
                        help='Will switch to outputting only empty items and will random sample up to specified --num-empty.')
    parser.add_argument('--num-empty', type=int, default=None,
                        help='Only for --empty-only. Specify the count of empty frames per sequence. By default saves all.')
    args = parser.parse_args()

    main(args)

