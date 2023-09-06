#!/usr/bin/env bash
./datum_create_dataset.py -j 40 --anno-path annos_bear_creek --proj-path datum_proj_bear_creek -f mot_seq_gt --export-path export_bear_creek     /mnt/disk5tb/sami_gdrive/comp_science/dataset/salmon_anno_bear_creek_123size.csv &> log.txt
