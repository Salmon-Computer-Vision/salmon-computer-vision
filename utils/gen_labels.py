#!/usr/bin/env python3

# Adapted from FairMOT
# https://github.com/ifzhang/FairMOT/blob/4aa62976bde6266cbafd0509e24c3d98a7d0899f/src/gen_labels_20.py

import os.path as osp
import os
import numpy as np
import argparse
from benedict import benedict


def mkdirs(d):
    if not osp.exists(d):
        os.makedirs(d)


def main(args):
    seq_root = args.seq_root
    label_root = args.label_root

    mkdirs(label_root)
    seqs = [s for s in os.listdir(seq_root)]

    tid_curr = 0
    tid_last = -1
    for seq in seqs:
        seq_dict = benedict.from_ini(osp.join(seq_root, seq, 'seqinfo.ini'))['Sequence']

        seq_width = int(seq_dict['imwidth'])
        seq_height = int(seq_dict['imheight'])

        gt_txt = osp.join(seq_root, seq, 'gt', 'gt.txt')
        gt = np.loadtxt(gt_txt, dtype=np.float64, delimiter=',')

        seq_label_root = osp.join(label_root, seq, 'img1')
        mkdirs(seq_label_root)

        for fid, tid, x, y, w, h, mark, label, _ in gt:
            if mark == 0:
                continue
            fid = int(fid)
            tid = int(tid)
            if not tid == tid_last:
                tid_curr += 1
                tid_last = tid
            x += w / 2
            y += h / 2
            label_fpath = osp.join(seq_label_root, '{:06d}.txt'.format(fid))
            label_str = '{} {:d} {:.6f} {:.6f} {:.6f} {:.6f}\n'.format(
                    label, tid_curr, x / seq_width, y / seq_height, w / seq_width, h / seq_height)
            with open(label_fpath, 'a') as f:
                f.write(label_str)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate JDE labels from MOT Seq GT')

    parser.add_argument('seq_root', help='Source MOT Sequences')
    parser.add_argument('--label_root', default='jde_labels', help='Destination JDE label folder')
    parser.set_defaults(func=main)

    args = parser.parse_args()
    args.func(args)
