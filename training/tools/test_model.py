import datumaro as dm
import os
from os import path as osp
import cv2
from matplotlib import pyplot as plt
import glob
from ultralytics import YOLO
from ultralytics import settings

import concurrent.futures
from functools import partial

import logging

import yaml
import pandas as pd

import argparse

# Evaluate model's performance on the test set
def test_model(data, weights, device=0):
    model = YOLO(weights)
    metrics = model.val(data=data, batch=512, device=device, split='test', imgsz=640)
    return metrics

def get_class_metrics(metrics, name):
    with open('2023_combined_salmon.yaml', 'r') as file:
        data = yaml.safe_load(file)

    class_names = [data['names'][ind] for ind in metrics.box.ap_class_index]
    
    df_classes = pd.DataFrame({
        'name': [name] * len(class_names),
        'class': class_names,
        'AP50': metrics.box.ap50,
        'Precision': metrics.box.p,
        'Recall': metrics.box.r,
        'mAP50': [metrics.box.map50] * len(class_names)
    })

    return df_classes


def parallel_test_model(train_key, test_key, dataset, model_id, device, result_queue):
    try:
        name = f'{train_key}{test_key}'
        logging.info(f'Testing {name} on device {device}')

        metrics = test_model(f'salm_dataset8010_yolo_{dataset}_2023/{yaml_file}',
                             f'runs/detect/train{model_id}/weights/best.pt',
                             device=device)
        df_classes = get_class_metrics(metrics, name)
        df_classes.to_csv(f'model_test_results_new/{name}.csv', index=False)
        
        # Here, you could return 'name' or any other identifier along with 'device' if needed
        result_queue.put((name, device))
    except Exception as e:
        logging.error(f"Error processing {name} on device {device}: {e}")
        # Return the device to the list in case of failure
        result_queue.put((None, device))

def manage_devices(datasets, model_id, yaml_file):
    num_devices = 4
    tasks = []
    
    # Create a queue to track task completion and device freeing
    from queue import Queue
    result_queue = Queue()
    for i in range(num_devices):
        result_queue.put((None, i))
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=num_devices) as executor:
        for test_key, dataset in datasets.items():
            for train_key, i in model_id.items():
                # Wait for a device to become available
                _, device = result_queue.get()
                
                logging.info('submit')
                # Submit a new task using the first available device
                task = executor.submit(parallel_test_model, train_key, test_key, dataset, i, device, result_queue)
                tasks.append(task)
                
        # Ensure all tasks are completed and devices are returned
        for task in concurrent.futures.as_completed(tasks):
            try:
                # Collect any remaining devices as tasks complete
                _, device = result_queue.get()
            except Exception as e:
                print(f"Task resulted in an error: {e}")

if __name__ == '__main__':
    # Update a setting
    logging.basicConfig(level=logging.INFO)
    settings.update({'runs_dir': '/training/runs'})

    # KiBeKoKw -> A, KiBe -> C, KoKw -> B
    # AA -> Trained on A, tested on A
    datasets = {'C': 'kitwanga_bear', 'B': 'koeye_kwakwa', 'A': 'kitwanga_bear_koeye_kwakwa'}
    model_ids = {'C': '36', 'B': '35', 'A': '33'}
    yaml_file = '2023_combined_salmon.yaml'

    #manage_devices(datasets, model_id, yaml_file)

    parser = argparse.ArgumentParser()
    parser.add_argument('train_key')
    parser.add_argument('test_key')
    parser.add_argument('device')
    args = parser.parse_args()

    train_key = args.train_key
    test_key = args.test_key
    device = int(args.device)
    model_id = model_ids[train_key]
    dataset = datasets[test_key]

    name = f'{train_key}{test_key}'
    logging.info(f'Testing {name} on device {device}')

    metrics = test_model(f'salm_dataset8010_yolo_{dataset}_2023/{yaml_file}',
                         f'runs/detect/train{model_id}/weights/best.pt',
                         device=device)
    df_classes = get_class_metrics(metrics, name)
    out_dir = 'model_test_results_pretrained'
    os.makedirs(out_dir, exist_ok=True)
    df_classes.to_csv(osp.join(out_dir, f'{name}.csv'), index=False)
