#!/usr/bin/env python3

import os
import argparse

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as md
import numpy as np
import seaborn
import glob

MEGAb_TO_b = 1e6
TCP_DOWN = "*down*[!udp]*.csv"
UDP_DOWN = "*down*udp*.csv"
TCP_UP = "*receive*[!udp]*.csv"
UDP_UP = "*receive*udp*.csv"

def combine_csvs(src):
    return pd.concat([pd.read_csv(f, index_col=0) for f in src])

def convert_to_mb(df):
    # Converts to Megabits per second
    df.bits_per_second /= MEGAb_TO_b
    df.rename(columns={'bits_per_second': 'bandwidth'}, inplace=True)

# TODO: Restrict plots to certain interesting days? (Rain, etc.)
# TODO: Plot power to bandwidth lineplot
# TODO: Plot weather to bandwidth/jitter histogram
# TODO: Plot bandwidth vs jitter/packet loss histogram or lineplot
# TODO: Compare TCP retransmits
# TODO: Compare different TCP methods


def plot_tcp_udp(args):
    combined_df_udp = combine_csvs(glob.glob(f"{args.src_folder}/**/*down*udp*.csv", recursive=True))
    
    combined_df_udp.index = pd.to_datetime(combined_df_udp.index, unit='s')
    convert_to_mb(combined_df_udp)
    combined_df_udp.drop(columns=['jitter_ms', 'lost_packets', 'packets', 'lost_percent'], inplace=True)
    combined_df_udp.rename(columns={'bandwidth': 'UDP'}, inplace=True)


    combined_df_tcp = combine_csvs(glob.glob(f"{args.src_folder}/**/*down*[!udp]*.csv", recursive=True))
    
    combined_df_tcp.index = pd.to_datetime(combined_df_tcp.index, unit='s')
    convert_to_mb(combined_df_tcp)
    combined_df_tcp.drop(columns=['jitter_ms', 'lost_packets', 'packets', 'lost_percent'], inplace=True)
    combined_df_tcp.rename(columns={'bandwidth': 'TCP'}, inplace=True)

    df_tcp_udp = pd.merge(combined_df_tcp, combined_df_udp, how='outer', left_index=True, right_index=True)

    print('TCP Avg:', df_tcp_udp.TCP.mean())
    print('UDP Avg:', df_tcp_udp.UDP.mean())
    print('Bandwidth ratio:', df_tcp_udp.TCP.mean() / df_tcp_udp.UDP.mean())
    print(df_tcp_udp.head())

    fig, ax = plt.subplots(figsize=(5,7))
    seaborn.boxplot(x="variable", y="value", data=pd.melt(df_tcp_udp), ax=ax)

    ax.set_xlabel("Methods", fontsize=12)
    ax.set_ylabel("Bandwidth (Mb/s)", fontsize=12)
    ax.tick_params(labelsize=12)
    if args.name:
        ax.set_title(args.name, fontsize=18)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')


def plot_reg(args):
    def combine_reg(pattern):
        regions_df = pd.DataFrame()
        first = True
        for region in os.scandir(args.src_folder):
            combined_df = combine_csvs(glob.glob(f"{region.path}/**/{pattern}", recursive=True))
            
            combined_df.index = pd.to_datetime(combined_df.index, unit='s')
            convert_to_mb(combined_df)
            combined_df.rename(columns={'bandwidth': region.name}, inplace=True)
            combined_df.drop(columns=['jitter_ms', 'lost_packets', 'packets', 'lost_percent'], inplace=True)

            if first:
                regions_df = combined_df
                first = False
            else:
                regions_df = pd.merge(regions_df, combined_df, how='outer', left_index=True, right_index=True)
        return regions_df

    df_down_tcp = combine_reg(TCP_DOWN)
    df_down_udp = combine_reg(UDP_DOWN)
    df_up_tcp = combine_reg(TCP_UP)
    df_up_udp = combine_reg(UDP_UP)

    fig, axs = plt.subplots(2, 2, sharey='row', sharex='col', figsize=(7.16,6))
    ax_big = fig.add_subplot(111, frameon=False)

    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_down_tcp), ax=axs[0, 0])
    boxplt.set(xlabel=None, ylabel="Download")
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_down_udp), ax=axs[0, 1])
    boxplt.set(xlabel=None, ylabel=None)
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1, 0])
    boxplt.set(xlabel="TCP", ylabel="Upload")
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1, 1])
    boxplt.set(xlabel="UDP", ylabel=None)
                
    axs[0,0].set_xticklabels([])
    axs[0,1].set_xticklabels([])
    for j in range(2):
        axs[1,j].set_xticklabels(labels=["Sao Paulo", "Singapore", "Sydney", "N. California", "Bahrain",
            "Tokyo", "London", "Mumbai"], rotation=45, ha='right', fontsize=9)

    ax_big.set_xlabel("Regions", fontsize=10, labelpad=80, fontweight='bold')
    ax_big.set_ylabel("Bandwidth (Mb/s)", fontsize=10, labelpad=50, fontweight='bold')
    ax_big.set_yticklabels([])
    ax_big.set_xticklabels([])
    ax_big.tick_params(
        which='both',
        bottom=False,
        left=False,
        right=False,
        top=False)
    ax_big.grid(False)
    if args.name:
        ax.set_title(args.name, fontsize=10)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')


def plot_single_avg(args):
    combined_df = combine_csvs(args.src_filenames)

    convert_to_mb(combined_df)

    if 'jitter_ms' in combined_df.columns:  # Assume UDP
        udp = True

    if args.save:
        combined_df.to_csv("combined.csv", encoding='utf-8-sig')

    fig, ax = plt.subplots(figsize=(5,7))
    seaborn.boxplot(x=combined_df.index.year, y=combined_df.bandwidth, ax=ax)

    ax.set_ylabel("Bandwidth (Mb/s)")
    if args.name:
        ax.set_title(args.name)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

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
    parser.add_argument('-n', '--name', help='The name of the plot')
    parser.add_argument('-f', '--filename', help='The name of the output image file', default='combined_plot')

    # TODO: use arg for type of plot and use dict to map option to default func
    days_parser = subp.add_parser("days")
    days_parser.set_defaults(func=plot_single_avg)
    days_parser.add_argument('src_filenames', nargs='*')
    days_parser.add_argument('-s', '--save', action='store_true', help='Will save the combined CSV')

    reg_parser = subp.add_parser("regions")
    reg_parser.set_defaults(func=plot_reg)
    reg_parser.add_argument('src_folder', help='Source folder with regions as direct subfolders')

    args = parser.parse_args()
    args.func(args)
