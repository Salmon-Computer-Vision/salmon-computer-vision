#!/usr/bin/env python3
import os
import xml.etree.ElementTree as ET
import concurrent.futures
from threading import Lock
from datumaro.components.dataset import Dataset
import argparse
import yaml

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

def write_error(file_path):
    with write_lock: # Safely write to error output files
        with open(error_output_file_path, 'a') as f:
            f.write(file_path + '\n')
            
def process_dataset(dataset_path, output_base_dir, no_filter=False, format=CVAT_FORMAT, save_media=False):
    # Process a single XML file: rename '__instance_id' to 'track_id', convert to Datumaro format and export.
    relative_path = os.path.relpath(dataset_path, start=original_root_dir)
    new_path = os.path.join(output_base_dir, relative_path)
    os.makedirs(os.path.dirname(new_path), exist_ok=True)
    output_dir = os.path.join(new_path, 'datumaro_format')
    
    import_path = new_path if format == CVAT_FORMAT else dataset_path

    output_anno = os.path.join(output_dir, 'annotations', 'default.json')
    output_empty = os.path.join(output_dir, 'annotations', 'empty')
    if os.path.exists(output_anno):
        print(f"Exists skipping... {output_anno}")
        return
    elif os.path.exists(output_empty):
        print(f"Empty exists skipping... {output_empty}")
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
            tree.write(new_path)

        # Convert to Datumaro format and export
        dataset = Dataset.import_from(import_path, format=format)
        dataset = dataset.transform('remap_labels', mapping=DUP_LABELS_MAPPING)
        dataset = dataset.transform('project_labels', dst_labels=LABELS_ORDER)
        if (not no_filter):
            dataset = dataset.filter('/item/annotation') # Must filter after remapping due to removed annotations
        try:
            dataset = dataset.transform('map_subsets', mapping={'output': 'default'})
        except Exception as e:
            print(f'Failed to map subset "output" to "default" likely no "output" subset: {e}')
        dataset.export(output_dir, format='datumaro', save_media=save_media)
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

def list_datasets(root_dir):
    for name in os.listdir(root_dir):
        yield os.path.join(root_dir, name)

def main(args):
    # Main function to process all 'output.xml' files found in the given directory.
    global original_root_dir
    global error_output_file_path
    global write_lock
    global LABELS_ORDER
    write_lock = Lock()
    original_root_dir = args.input_directory
    error_output_file_path = os.path.join(args.output_directory, 'error_files.txt')
    
    with open(args.labels_file, 'r') as file:
        data = yaml.safe_load(file)
    LABELS_ORDER = list(data['names'].values())

    if args.format == 'cvat':
        datasets = list(find_xml_files(args.input_directory))
    else:
        datasets = list(list_datasets(args.input_directory))

    # Process each file in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as executor:
        # Create a partial function call including the output base directory
        from functools import partial
        process_file = partial(process_dataset, output_base_dir=args.output_directory, 
                               no_filter=args.no_filter, format=args.format, save_media=args.save_media)
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
    parser.add_argument('-f', '--format', default='cvat',
                        help='Input format of annotations for Datumaro to import')
    parser.add_argument('--save-media', action='store_true',
                        help='Save media in output folder')
    args = parser.parse_args()

    main(args)

