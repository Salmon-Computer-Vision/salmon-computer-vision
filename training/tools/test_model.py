import datumaro as dm
import os
from os import path as osp
import cv2
from matplotlib import pyplot as plt
import glob
from ultralytics import YOLO
from ultralytics import settings

# Update a setting
settings.update({'runs_dir': '/training/runs'})


import yaml
import pandas as pd

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

datasets = ['kitwanga_bear', 'koeye_kwakwa', 'kitwanga_bear_koeye_kwakwa']
yaml_file = '2023_combined_salmon.yaml'

# KiBeKoKw -> A, KiBe -> C, KoKw -> B
# AA -> Trained on A, tested on A
metrics = test_model('salm_dataset8010_yolo_kitwanga_bear_2023/2023_combined_salmon.yaml','runs/detect/train31/weights/best.pt', device=1)
df_classes = get_class_metrics(metrics, 'CC')
df_classes.to_csv('model_test_results/CC.csv', index=False)