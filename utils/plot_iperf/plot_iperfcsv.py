#!/usr/bin/env python3

import os
import argparse

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as md
import numpy as np
import seaborn

MEGAb_TO_b = 1e6

def combine_csvs(src):
    return pd.concat([pd.read_csv(f, index_col=0) for f in src])

def convert_to_mb(df):
    # Converts to Megabits per second
    df.bits_per_second /= MEGAb_TO_b
    df.rename(columns={'bits_per_second': 'bandwidth'}, inplace=True)

def plot_days(args):
    combined_df = combine_csvs(args.src_filenames)
    combined_df.index = pd.to_datetime(combined_df.index, unit='s')

    convert_to_mb(combined_df)

    #combined_df = combined_df.resample('d').mean()
    #print(combined_df.head())
    print(combined_df.bandwidth.max())

    if 'jitter_ms' in combined_df.columns:  # Assume UDP
        udp = True

    if args.save:
        combined_df.to_csv("combined.csv", encoding='utf-8-sig')

    fig, ax = plt.subplots(figsize=(12,7))
    seaborn.boxplot(x=combined_df.index.dayofyear, y=combined_df.bandwidth, ax=ax)
    #seaborn.lineplot(x=combined_df.index.dayofyear, y=combined_df.bandwidth, ax=ax)

    # Converts timestamps to month-day labels and displays them
    x_dates = combined_df.index.strftime('%m-%d').sort_values().unique()
    ax.set_xticklabels(labels=x_dates, rotation=45, ha='right')

    ax.set_xlabel("Day of Month (2022)")
    ax.set_ylabel("Bandwidth (Mb/s)")
    if args.name:
        ax.set_title(args.name)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Plot iperf CSV files of format [timestamp, bits_per_second].')
    subp = parser.add_subparsers(help="Different visualizations")

    days_parser = subp.add_parser("days")
    days_parser.set_defaults(func=plot_days)
    days_parser.add_argument('src_filenames', nargs='*')
    days_parser.add_argument('-s', '--save', action='store_true', help='Will save the combined CSV')
    days_parser.add_argument('-n', '--name', help='The name of the plot')
    days_parser.add_argument('-f', '--filename', help='The name of the output image file', default='combined_plot')

    args = parser.parse_args()
    args.func(args)
