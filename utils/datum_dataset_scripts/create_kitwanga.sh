#!/usr/bin/env bash
./datum_create_dataset.py -j 64 \
    --anno-path /mnt/shiorissd4tb/masamim/annos_kitwanga \
    --proj-path datum_proj_kitwanga \
    --skip-preprocessing \
    -f yolo --export-path /mnt/shiorissd4tb/masamim/export_kitwanga_all \
    /mnt/disk5tb/masamim/sami_gdrive/comp_science/dataset/salmon_anno_kitwanga_1587size.csv &> log.txt

#./datum_create_dataset.py -j 64 --anno-path /mnt/shiorissd4tb/masamim/annos_kitwanga --proj-path datum_proj_kitwanga  -f mot_seq_gt --export-path export_kitwanga     /mnt/disk5tb/sami_gdrive/comp_science/dataset/salmon_anno_kitwanga_1587size.csv &> log.txt
