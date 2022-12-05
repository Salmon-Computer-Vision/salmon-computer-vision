#!/usr/bin/env python3

import os
import os.path as osp
import argparse
import logging as log

log.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=log.INFO,
        datefmt='%Y-%m-%d %H:%M:%S')

KEY_TEST = 'test'
KEY_VALID = 'valid'
KEY_TRAIN = 'train'
KEY_BACKUP = 'backup'
PREFIX = 'data/'

def main(args):
    src_path = osp.abspath(args.src_folder)
    os.makedirs(osp.join(src_path, KEY_BACKUP), exist_ok=True)
    set_keys = [KEY_TEST, KEY_VALID, KEY_TRAIN]

    for set_key in set_keys:
        log.info(f'Consolidating {set_key} set...')

        set_path = osp.join(src_path, set_key)
        text_path = osp.join(src_path, f"{set_key}.txt")
        with open(text_path, 'w') as d:
            for seq in os.listdir(set_path):
                seq_path = osp.join(set_path, seq)
                seq_text_path = osp.join(seq_path, f"{KEY_TRAIN}.txt")
                sd = open(seq_text_path, 'r')
                rel_paths = sd.readlines()
                [d.write(osp.join(seq_path, rel_path[len(PREFIX):])) for rel_path in rel_paths]
                


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Consolidate train, valid, test folders from the create dataset script into one text file each.')

    parser.add_argument('src_folder', help='YOLO datasets folder')
    parser.set_defaults(func=main)

    args = parser.parse_args()
    args.func(args)
