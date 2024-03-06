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
        'Juvenile Salmonoid': None,
        'Juvenile coho salmon': None,
        }

def write_error(file_path):
    with write_lock: # Safely write to error output files
        with open(error_output_file_path, 'a') as f:
            f.write(file_path + '\n')
            
def process_xml_file(file_path, output_base_dir):
    # Process a single XML file: rename '__instance_id' to 'track_id', convert to Datumaro format and export.
    relative_path = os.path.relpath(file_path, start=original_root_dir)
    new_file_path = os.path.join(output_base_dir, relative_path)
    os.makedirs(os.path.dirname(new_file_path), exist_ok=True)
    output_dir = os.path.join(os.path.dirname(new_file_path), 'datumaro_format')

    """
    if os.path.exists(output_dir):
        print(f"Exists skipping... {output_dir}")
        return
    """
        
    try:
        # Load and Transform CVAT XML
        tree = ET.parse(file_path)
        root = tree.getroot()

        # Find the attribute with name "__instance_id" and rename it to "track_id"
        for elem in root.iter('attribute'):
            if elem.get('name') == '__instance_id':
                elem.set('name', 'track_id')
            
        # Save the modified XML to a new file in the new output directory
        tree.write(new_file_path)

        # Convert to Datumaro format and export
        dataset = Dataset.import_from(new_file_path, format="cvat")
        dataset = dataset.transform('remap_labels', mapping=DUP_LABELS_MAPPING)
        dataset = dataset.transform('project_labels', dst_labels=LABELS_ORDER)
        dataset = dataset.filter('/item/annotation') # Must filter after remapping due to removed annotations
        dataset = dataset.transform('map_subsets', mapping={'output': 'default'})
        dataset.export(output_dir, format='datumaro', save_media=False)
        
    except ET.ParseError as e:
        print(f"Parse error processing file {file_path}: {e}")
        write_error(file_path)
    except Exception as e:
        print(f"Error processing file {file_path}: {e}")
        write_error(file_path)

def find_xml_files(root_dir):
    # Recursively search for all 'output.xml' files within a given directory.
    for subdir, dirs, files in os.walk(root_dir):
        for filename in files:
            if filename == 'output.xml':
                yield os.path.join(subdir, filename)

def main(root_dir, output_base_dir, max_workers=None):
    # Main function to process all 'output.xml' files found in the given directory.
    global original_root_dir
    global error_output_file_path
    global write_lock
    global LABELS_ORDER
    write_lock = Lock()
    original_root_dir = root_dir
    error_output_file_path = os.path.join(output_base_dir, 'error_files.txt')
    
    with open('../../2023_combined_salmon.yaml', 'r') as file:
        data = yaml.safe_load(file)
    LABELS_ORDER = list(data['names'].values())
    
    xml_files = list(find_xml_files(root_dir))

    # Process each file in parallel
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Create a partial function call including the output base directory
        from functools import partial
        process_file = partial(process_xml_file, output_base_dir=output_base_dir)
        executor.map(process_file, xml_files)

# Command-line interface setup
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Process CVAT XML files in parallel and convert them to Datumaro format.')
    parser.add_argument('input_directory', help='Root directory containing the CVAT XML files')
    parser.add_argument('output_directory', help='Root directory for saving the processed files and Datumaro datasets')
    parser.add_argument('--workers', type=int, default=None,
                        help='Maximum number of threads to use. Defaults to the number of CPU cores if not set.')
    args = parser.parse_args()

    main(args.input_directory, args.output_directory, max_workers=args.workers)

