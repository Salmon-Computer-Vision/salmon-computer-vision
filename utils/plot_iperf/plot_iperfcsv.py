#!/usr/bin/env python3

import os
import argparse

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as md
import numpy as np
import seaborn
import glob

from dateutil import tz

MEGAb_TO_b = 1e6
TCP_DOWN = "*down*[!udp]*.csv"
UDP_DOWN = "*down*udp*.csv"
TCP_UP = "*receive*[!udp]*.csv"
UDP_UP = "*receive*udp*.csv"
TEMP='Temp (°C)'
PRECIP='Precip. Amount (mm)'

JITTER = 'jitter_ms'

def combine_csvs(src, ind_col=0):
    return pd.concat([pd.read_csv(f, index_col=ind_col) for f in src])


def convert_to_mb(df):
    # Converts to Megabits per second
    df.bits_per_second /= MEGAb_TO_b
    df.rename(columns={'bits_per_second': 'bandwidth'}, inplace=True)


def concat_df(src, pattern, keep=['bandwidth']):
    combined_df = combine_csvs(glob.glob(f"{src}/**/{pattern}", recursive=True))
    
    combined_df.index = pd.to_datetime(combined_df.index, unit='s')
    convert_to_mb(combined_df)
    combined_df = combined_df[keep]
    return combined_df

# TODO: Restrict plots to certain interesting days? (Rain, etc.)
# TODO: Plot power to bandwidth lineplot
# TODO: Plot weather to bandwidth/jitter histogram
# TODO: Plot bandwidth vs jitter/packet loss histogram or lineplot
# TODO: Compare TCP retransmits
# TODO: Compare different TCP methods

def plot_time(args):
    df_down_udp = concat_df(args.src_folder, UDP_DOWN, [JITTER])
    #df_down_udp = concat_df(args.src_folder, UDP_DOWN)
    #df_down_udp = df_down_udp.loc['2022-03-01 04':'2022-03-01 04']
    #df_down_udp = df_down_udp.loc['2022-03-01 04:07:30':'2022-03-01 04:08:40']
    #df_down_udp = df_down_udp.loc['2022-03-01':'2022-03-02']

    fig, ax = plt.subplots(figsize=(7.16,5))
    ax.xaxis.update_units(df_down_udp.index)
    seaborn.scatterplot(x=ax.xaxis.convert_units(df_down_udp.index), y=df_down_udp.jitter_ms, ax=ax)
    ax.set(yscale='log')
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('right')

    ax.set_ylabel("Jitter (ms)")
    #ax.set_ylabel("Bandwidth (Mb/s)")
    if args.name:
        ax.set_title(args.name)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')
    plt.show()

def plot_thr_weather(args):
    df_down_udp = concat_df(args.src_folder, UDP_DOWN, [JITTER])
    df_down_udp = df_down_udp.resample('H').mean()
    df_down_udp.index = df_down_udp.index.tz_localize('UTC')
    print(df_down_udp.head())

    df_weather = combine_csvs(glob.glob(os.path.join(args.src_weather, '*.csv')), 4)
    df_weather.index = pd.to_datetime(df_weather.index).tz_localize(tz.tzlocal())
    df_weather = df_weather[[PRECIP]]
    
    df_merged = df_down_udp.merge(df_weather, left_index=True, right_index=True, how='inner').drop_duplicates()
    #print(df_merged.head())
    #print(df_merged[df_merged.columns[1]].count())

    if args.save:
        df_merged.to_csv("combined.csv", encoding='utf-8-sig')

    
    #fig, ax = plt.subplots(figsize=(3.5,2))
    fig, ax = plt.subplots(figsize=(7.16,5))
    #seaborn.scatterplot(x=df_merged.iloc[:, 1], y=df_merged.jitter_ms, ax=ax)
    seaborn.scatterplot(x=df_merged.index, y=df_merged.iloc[:, 1], ax=ax)
    seaborn.despine()

    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('right')

    #ax.set_xlabel("Day of Month (2022)")
    #ax.set_ylabel("Jitter (m)")
    if args.name:
        ax.set_title(args.name)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')


def avg_jitter(args):
    df_down = concat_df(args.src_folder, UDP_DOWN, [JITTER])
    df_up = concat_df(args.src_folder, UDP_UP, [JITTER])

    print('UDP Down Jitter:', df_down.jitter_ms.mean())
    print('UDP Up Jitter:', df_up.jitter_ms.mean())


def plot_tcp_udp(args):
    df_down_tcp = concat_df(args.src_folder, TCP_DOWN)
    df_down_tcp.rename(columns={'bandwidth': 'TCP'}, inplace=True)

    df_down_udp = concat_df(args.src_folder, UDP_DOWN)
    df_down_udp.rename(columns={'bandwidth': 'UDP'}, inplace=True)

    df_up_tcp = concat_df(args.src_folder, TCP_UP)
    df_up_tcp.rename(columns={'bandwidth': 'TCP'}, inplace=True)

    df_up_udp = concat_df(args.src_folder, UDP_UP)
    df_up_udp.rename(columns={'bandwidth': 'UDP'}, inplace=True)

    df_tcp_udp_down = pd.merge(df_down_tcp, df_down_udp, how='outer', left_index=True, right_index=True)
    df_tcp_udp_up = pd.merge(df_up_tcp, df_up_udp, how='outer', left_index=True, right_index=True)

    print('TCP Down Avg:', df_tcp_udp_down.TCP.mean())
    print('UDP Down Avg:', df_tcp_udp_down.UDP.mean())
    print('TCP Up Avg:', df_tcp_udp_up.TCP.mean())
    print('UDP Up Avg:', df_tcp_udp_up.UDP.mean())
    print('Bandwidth Down ratio:', df_tcp_udp_down.TCP.mean() / df_tcp_udp_down.UDP.mean())
    print('Bandwidth Down ratio:', df_tcp_udp_up.TCP.mean() / df_tcp_udp_up.UDP.mean())
    print(df_tcp_udp_down.head())

    fig, ax = plt.subplots(figsize=(3.5,2))
    seaborn.boxplot(x="variable", y="value", data=pd.melt(df_tcp_udp_down), ax=ax)

    ax.set_xlabel("Methods", fontsize=10)
    ax.set_ylabel("Bandwidth (Mb/s)", fontsize=10)
    ax.tick_params(labelsize=9)
    if args.name:
        ax.set_title(args.name, fontsize=10)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

def combine_reg(src, pattern, keep='bandwidth'):
    regions_df = pd.DataFrame()
    first = True
    for region in os.scandir(src):
        combined_df = concat_df(region.path, pattern, [keep])
        combined_df.rename(columns={keep: region.name}, inplace=True)

        if first:
            regions_df = combined_df
            first = False
        else:
            regions_df = pd.merge(regions_df, combined_df, how='outer', left_index=True, right_index=True)
    return regions_df


def plot_jitter_100(args):
    df_down_udp = combine_reg(args.src_folder, UDP_DOWN, JITTER)
    df_down_udp = df_down_udp[ df_down_udp.iloc[:,:] >= 100 ].dropna(how='all')
    print(df_down_udp.head())
    #df_up_udp = combine_reg(args.src_folder, UDP_UP, JITTER)

    if args.save:
        df_down_udp.to_csv("combined.csv", encoding='utf-8-sig')


def plot_reg_udp_only(args):
    df_down_udp = combine_reg(args.src_folder, UDP_DOWN, [JITTER])
    print(df_down_udp.head())
    df_up_udp = combine_reg(args.src_folder, UDP_UP, [JITTER])

    fig, axs = plt.subplots(1, 2, sharey='row', sharex='col', figsize=(7.16,3))
    ax_big = fig.add_subplot(111, frameon=False)

    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_down_udp), ax=axs[0])
    boxplt.set(xlabel='Download', ylabel=None)
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1])
    boxplt.set(xlabel='Upload', ylabel=None)
                
    for j in range(2):
        axs[j].set(yscale='log')
        axs[j].set_xticklabels(labels=["Sao Paulo", "Singapore", "Sydney", "N. California", "Bahrain",
            "Tokyo", "London", "Mumbai"], rotation=45, ha='right', fontsize=9)

    ax_big.set_xlabel("Regions", fontsize=10, labelpad=80, fontweight='bold')
    ax_big.set_ylabel("Jitter (ms)", fontsize=10, labelpad=40, fontweight='bold')
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

def plot_reg(args):
    df_down_tcp = combine_reg(args.src_folder, TCP_DOWN)
    df_down_udp = combine_reg(args.src_folder, UDP_DOWN)
    print(df_down_udp.head())
    df_up_tcp = combine_reg(args.src_folder, TCP_UP)
    df_up_udp = combine_reg(args.src_folder, UDP_UP)

    fig, axs = plt.subplots(2, 2, sharey='row', sharex='col', figsize=(7.16,6))
    ax_big = fig.add_subplot(111, frameon=False)

    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_down_tcp), ax=axs[0, 0])
    boxplt.set(xlabel=None, ylabel="Download")
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_down_udp), ax=axs[0, 1])
    boxplt.set(xlabel=None, ylabel=None)
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_up_tcp), ax=axs[1, 0])
    boxplt.set(xlabel="TCP", ylabel="Upload")
    boxplt = seaborn.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1, 1])
    boxplt.set(xlabel="UDP", ylabel=None)
                
    axs[0,0].set_xticklabels([])
    axs[0,1].set_xticklabels([])
    for j in range(2):
        axs[1,j].set_xticklabels(labels=["Sao Paulo", "Singapore", "Sydney", "N. California", "Bahrain",
            "Tokyo", "London", "Mumbai"], rotation=45, ha='right', fontsize=9)

    #for i in range(2):
    #    for j in range(2):
    #        axs[i,j].set(yscale='log')

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
    parser.add_argument('-s', '--save', action='store_true', help='Will save the combined CSV')

    # TODO: use arg for type of plot and use dict to map option to default func
    days_parser = subp.add_parser("days")
    days_parser.set_defaults(func=plot_single_avg)
    days_parser.add_argument('src_filenames', nargs='*')

    reg_parser = subp.add_parser("regions")
    reg_parser.set_defaults(func=plot_time)
    reg_parser.add_argument('src_folder', help='Source folder with regions as direct subfolders')

    weather_parser = subp.add_parser("weather")
    weather_parser.set_defaults(func=plot_thr_weather)
    weather_parser.add_argument('src_folder', help='Source bandwidth CSV folder')
    weather_parser.add_argument('src_weather', help='Source climate CSV folder')

    args = parser.parse_args()
    args.func(args)
