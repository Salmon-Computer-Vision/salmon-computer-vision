#!/usr/bin/env bash
./datum_create_dataset.py -j 64 --anno-path /mnt/shiorissd4tb/masamim/annos_kitwanga --proj-path datum_proj_kitwanga  -f mot_seq_gt --export-path export_kitwanga     /mnt/disk5tb/sami_gdrive/comp_science/dataset/salmon_anno_kitwanga_1587size.csv &> log.txt
