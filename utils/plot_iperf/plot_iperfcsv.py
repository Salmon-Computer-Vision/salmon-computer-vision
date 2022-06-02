#!/usr/bin/env python3

import os
import argparse

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as md
import numpy as np
import seaborn as sns
import glob
from scipy import stats

from dateutil import tz

MEGAb_TO_b = 1e6
TCP_DOWN = "*down.*.csv"
UDP_DOWN = "*down*udp*.csv"
TCP_UP = "*receive.*[!p].csv"
UDP_UP = "*receive*.udp.csv"
TEMP='Temp (°C)'
PRECIP='Precip. Amount (mm)'

JITTER = 'jitter_ms'
BANDWIDTH = 'bandwidth'

def set_pubfig():
    sns.set_context("paper", rc={"font.size":9,"axes.titlesize":9,"axes.labelsize":8, "xtick.labelsize":8})

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
    #df = concat_df(args.src_folder, UDP_UP, [JITTER])
    df = combine_reg(args.src_folder, TCP_DOWN, first=4)
    df_unstacked = df.unstack().dropna()
    df_unstacked = df_unstacked.mask(df_unstacked == -1).reset_index(name=BANDWIDTH).set_index('timestamp')
    df_regs = df.replace(-1, pd.NA).dropna(how='all')
    #df = concat_df(args.src_folder, UDP_DOWN).sort_values('timestamp')
    #df = df.loc['2022-03-02 14:02:00':'2022-03-02 14:10:00']
    #df = df.loc['2022-03-01 04:07:30':'2022-03-01 04:08:40']
    #df = df.loc['2022-03-01':'2022-03-02']

    # Aggreagation options
    print(df_regs)
    df_regs = df_regs.astype(float).resample('2T').mean()
    print(df_regs.head())

    #df.to_csv("out.csv", encoding='utf-8-sig')

    print(df_unstacked.shape[0])

    #fig, ax = plt.subplots(figsize=(3.5,3))
    fig, ax = plt.subplots(figsize=(20,10))
    ax.xaxis.update_units(df.index)
    y_val = df_unstacked.bandwidth
    #sns.scatterplot(x=ax.xaxis.convert_units(df.timestamp), y=y_val, ax=ax)
    #sns.jointplot(x=ax.xaxis.convert_units(df.timestamp), y=y_val, ax=ax)

    #sns.lineplot(x=ax.xaxis.convert_units(df.index), y=y_val, ax=ax, hue=y_val.isna().cumsum(),
    #        palette=["black"]*sum(y_val.isna()), markers=True, legend=False)
    sns.lineplot(data=df_regs)
    #ax.set(yscale='log')
    for label in ax.get_xticklabels():
        label.set_rotation(45)
        label.set_ha('right')

    #ax.set_ylabel("Jitter (ms)")
    ax.set_ylabel("Bandwidth (Mb/s)")
    if args.name:
        ax.set_title(args.name)

    plt.tight_layout()
    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')
    plt.show()

def plot_thr_weather(args):
    df_down_udp = concat_df(args.src_folder, UDP_DOWN, [BANDWIDTH])
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
    #sns.scatterplot(x=df_merged.iloc[:, 1], y=df_merged.jitter_ms, ax=ax)
    sns.scatterplot(x=df_merged.index, y=df_merged.iloc[:, 1], ax=ax)
    sns.despine()

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

def plot_multi(args):
    COL = JITTER
    YLABEL = "Jitter (ms)"

    df_all = pd.DataFrame()
    for folder in args.src_dirs:
        df = concat_df(folder, UDP_UP, [COL])
        df.rename(columns={COL: folder}, inplace=True)
        df_all = df_all.merge(df, how='outer', left_index=True, right_index=True)

    #zsc = np.abs(stats.zscore(df_all, nan_policy='omit'))
    #print(zsc)
    #df_all = df_all[(np.less(zsc, 2., where=np.isfinite(zsc))).all(axis=1)]
    df_all = df_all[df_all < 10]
    print(df_all.head())
    print(df_all.iloc[:,1].mean())

    fig, ax = plt.subplots(figsize=(3.5,2))
    #ax.set(yscale='log')
    sns.boxplot(x="variable", y="value", data=pd.melt(df_all), ax=ax, showfliers=False)

    ax.set_xticklabels(labels=["Shaw", "Starlink"], fontsize=9)

    ax.set_xlabel("Network Provider", fontsize=10)
    ax.set_ylabel(YLABEL, fontsize=10)
    ax.tick_params(labelsize=9)
    if args.name:
        ax.set_title(args.name, fontsize=10)

    fig.tight_layout()
    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

def plot_tcp_udp(args):
    COL = JITTER
    df_down_tcp = concat_df(args.src_folder, TCP_DOWN, [COL])
    df_down_tcp.rename(columns={COL: 'TCP'}, inplace=True)

    df_down_udp = concat_df(args.src_folder, UDP_DOWN, [COL])
    df_down_udp.rename(columns={COL: 'UDP'}, inplace=True)

    df_up_tcp = concat_df(args.src_folder, TCP_UP, [COL])
    df_up_tcp.rename(columns={COL: 'TCP'}, inplace=True)

    df_up_udp = concat_df(args.src_folder, UDP_UP, [COL])
    df_up_udp.rename(columns={COL: 'UDP'}, inplace=True)

    df_tcp_udp_down = pd.merge(df_down_tcp, df_down_udp, how='outer', left_index=True, right_index=True)
    df_tcp_udp_up = pd.merge(df_up_tcp, df_up_udp, how='outer', left_index=True, right_index=True)

    print('TCP Down Avg:', df_tcp_udp_down.TCP.mean())
    print('TCP Down Max:', df_tcp_udp_down.TCP.max())
    print('UDP Down Avg:', df_tcp_udp_down.UDP.mean())
    print('UDP Down Max:', df_tcp_udp_down.UDP.max())
    print('TCP Up Avg:', df_tcp_udp_up.TCP.mean())
    print('TCP Up Max:', df_tcp_udp_up.TCP.max())
    print('UDP Up Avg:', df_tcp_udp_up.UDP.mean())
    print('UDP Up Max:', df_tcp_udp_up.UDP.max())
    print('Bandwidth Down ratio:', df_tcp_udp_down.TCP.mean() / df_tcp_udp_down.UDP.mean())
    print('Bandwidth Down ratio:', df_tcp_udp_up.TCP.mean() / df_tcp_udp_up.UDP.mean())
    print(df_tcp_udp_down.head())

    fig, ax = plt.subplots(figsize=(3.5,2))
    sns.boxplot(x="variable", y="value", data=pd.melt(df_tcp_udp_down), ax=ax)

    ax.set_xlabel("Methods", fontsize=10)
    ax.set_ylabel("Bandwidth (Mb/s)", fontsize=10)
    ax.tick_params(labelsize=9)
    if args.name:
        ax.set_title(args.name, fontsize=10)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

def remove_first_measures(df, first=3):
    # Remove first {first} datapoints for each measurement
    # Take into account of software tool overhead
    diff_time = (df.index - df.reset_index().timestamp.shift())
    # Choose entries where previous time is less than an hour
    first_measure_map = diff_time < pd.Timedelta(5, unit='m')
    # Propagate to first three datapoints
    for i in range(1, first):
        first_measure_map = first_measure_map.eq(first_measure_map.shift(i))

    df_map = pd.DataFrame(columns=df.columns)
    df_map.iloc[:,0] = first_measure_map
    df_map['timestamp'] = df.index
    df_map.set_index('timestamp', inplace=True)
    filtered_df = df.where(df_map, -1) # Set to -1

    return filtered_df

def combine_reg(src, pattern, keep='bandwidth', first=3):
    regions_df = pd.DataFrame()
    start = True
    for region in os.scandir(src):
        combined_df = concat_df(region.path, pattern, [keep]).sort_values('timestamp')
        combined_df.rename(columns={keep: region.name}, inplace=True)
        combined_df = remove_first_measures(combined_df, first)

        if start:
            regions_df = combined_df
            start = False
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
    df_down_udp = combine_reg(args.src_folder, UDP_DOWN, JITTER)
    print(df_down_udp.head())
    df_up_udp = combine_reg(args.src_folder, UDP_UP, JITTER)

    fig, axs = plt.subplots(1, 2, figsize=(7.16,5))
    ax_big = fig.add_subplot(111, frameon=False)

    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_down_udp), ax=axs[0], showfliers=False)
    boxplt.set(xlabel='Download', ylabel=None)
    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1], showfliers=False)
    boxplt.set(xlabel='Upload', ylabel=None)
                
    for j in range(2):
        #axs[j].set(yscale='log')
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

    fig.tight_layout()
    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

def plot_reg(args):
    df_down_tcp = combine_reg(args.src_folder, TCP_DOWN)
    df_down_udp = combine_reg(args.src_folder, UDP_DOWN)
    print(df_down_udp.head())
    df_up_tcp = combine_reg(args.src_folder, TCP_UP)
    df_up_udp = combine_reg(args.src_folder, UDP_UP)

    fig, axs = plt.subplots(2, 2, sharey='row', sharex='col', figsize=(7.16,6))
    ax_big = fig.add_subplot(111, frameon=False)

    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_down_tcp), ax=axs[0, 0])
    boxplt.set(xlabel=None, ylabel="Download")
    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_down_udp), ax=axs[0, 1])
    boxplt.set(xlabel=None, ylabel=None)
    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_up_tcp), ax=axs[1, 0])
    boxplt.set(xlabel="TCP", ylabel="Upload")
    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_up_udp), ax=axs[1, 1])
    boxplt.set(xlabel="UDP", ylabel=None)
                
    axs[0,0].set_xticklabels([])
    axs[0,1].set_xticklabels([])
    for j in range(2):
        axs[1,j].set_xticklabels(labels=["Sao Paulo", "Singapore", "Sydney", "N. California", "Bahrain",
            "Tokyo", "London", "Mumbai"], rotation=45, ha='right', fontsize=9)
        #axs[1,j].set_xticklabels(labels=["Sydney", "N. California"], rotation=45, ha='right', fontsize=9)
        for label in axs[1,j].get_xticklabels():
            label.set_rotation(45)
            label.set_ha('right')


    if args.save:
        df_down_udp.to_csv("combined.csv", encoding='utf-8-sig')
    #for i in range(2):
    #    for j in range(2):
    #        axs[i,j].set(yscale='log')

    ax_big.set_xlabel("Regions", fontsize=9, labelpad=80, fontweight='bold')
    ax_big.set_ylabel("Bandwidth (Mb/s)", fontsize=9, labelpad=50, fontweight='bold')
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
        ax.set_title(args.name, fontsize=9)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')


def plot_single_avg(args):
    combined_df = combine_csvs(args.src_filenames)

    convert_to_mb(combined_df)

    if 'jitter_ms' in combined_df.columns:  # Assume UDP
        udp = True

    if args.save:
        combined_df.to_csv("combined.csv", encoding='utf-8-sig')

    fig, ax = plt.subplots(figsize=(5,7))
    sns.boxplot(x=combined_df.index.year, y=combined_df.bandwidth, ax=ax)

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
    sns.boxplot(x=combined_df.index.dayofyear, y=combined_df.bandwidth, ax=ax)
    #sns.lineplot(x=combined_df.index.dayofyear, y=combined_df.bandwidth, ax=ax)

    # Converts timestamps to month-day labels and displays them
    x_dates = combined_df.index.strftime('%m-%d').sort_values().unique()
    ax.set_xticklabels(labels=x_dates, rotation=45, ha='right')

    ax.set_xlabel("Day of Month (2022)")
    ax.set_ylabel("Bandwidth (Mb/s)")
    if args.name:
        ax.set_title(args.name)

    plt.savefig(f'{args.filename}.eps', format='eps', bbox_inches='tight')

def plot_ping(args):
    N_STARLINK = 'Starlink'
    N_SHAW = 'Shaw'

    df = pd.DataFrame()
    for folder in args.src_dirs:
        for region in os.scandir(folder):
            pattern = f"{region.path}/*"
            print(pattern)
            df_temp = combine_csvs(glob.glob(pattern, recursive=True), 3)
            df_temp.index = pd.to_datetime(df_temp.index, unit='s')
            df_temp = df_temp.iloc[:,[2]]
            df_temp.rename(columns={df_temp.columns[0]: f"{folder}_{region.name}"}, inplace=True)

            df = df.merge(df_temp, how='outer', left_index=True, right_index=True)

    print(df.shape[0])
    df = df.sample(10000)
    num_regs = int(len(df.columns) / 2) # One for each of Shaw vs Starlink
    print(num_regs)
    cols = df.columns.tolist()

    print(df.head())
    new_cols = []
    #for col in cols:
    #    region = col.split('/')[1].replace('_',' ').strip()
    #    new_cols.append(region)
    new_cols = ['Mumbai', 'Sydney', 'Singapore', 
            'N. California', 'London', 'Bahrain', 'Sao Paulo', 'Tokyo', 'Africa'] * 2
    multi_cols = [
            [N_SHAW] * num_regs + [N_STARLINK] * num_regs,
            new_cols
            ]
    df.set_axis(multi_cols, axis=1, inplace=True)
    print(df.head())

    N_REGIONS = 'Regions'
    df = df.unstack().reset_index(name='latency').dropna()
    df.rename(columns={'level_0': 'type', 'level_1': N_REGIONS, 'level_2': 'timestamp'},
            inplace=True)
    print(df.head())

    #df_pivot = df.pivot_table(index=[N_REGIONS, 'timestamp'], columns='type', values='latency')
    #print(df_pivot.head())

    g = sns.catplot(data=df, x='type', y='latency', col=N_REGIONS, col_wrap=4, kind='box', height=2,
            aspect=0.895, showfliers=True)
    g.set(yscale='log')
    g.tight_layout()
    (g.set_axis_labels('Provider', 'Latency (ms)')
            .set_titles("{col_name}"))


    ########
    #df = df.loc['2022-04-14 04':'2022-04-15 04']

    #fig, ax = plt.subplots(figsize=(3.5,2))
    #ax.xaxis.update_units(df.index)
    #sns.lineplot(x=ax.xaxis.convert_units(df.index), y=df.iloc[:,0], ax=ax)
    #sns.lineplot(x=df.index, y=df.iloc[:,0], ax=ax)

    #for label in ax.get_xticklabels():
    #    label.set_rotation(45)
    #    label.set_ha('right')
    #ax.set_ylabel('Latency (ms)')
    #########

    ########
    #fig, axs = plt.subplots(1, num_regs, figsize=(7.16,5))
    #ax_big = fig.add_subplot(111, frameon=False)

    #df_regions = []
    #for i in range(num_regs):
    #    df_region = df.iloc[:,[i,(num_regs+i)]]
    #    boxplt = sns.boxplot(x="variable", y="value", data=pd.melt(df_region), ax=axs[i], showfliers=False)

    #    raw_region = df_region.columns[0]
    #    region = raw_region.split('/')[1].replace('_',' ').strip()
    #    boxplt.set(xlabel=region, ylabel=None)

    #    #axs[i].set(yscale='log')
    #    axs[i].set_xticklabels(labels=["Shaw", "Starlink"], fontsize=9)
    #    axs[i].tick_params(labelsize=9)


    #ax_big.set_xlabel("Network Provider and Region", fontsize=10, labelpad=30, fontweight='bold')
    #ax_big.set_ylabel("Latency (ms)", fontsize=10, labelpad=30, fontweight='bold')
    #ax_big.set_yticklabels([])
    #ax_big.set_xticklabels([])
    #ax_big.tick_params(
    #    which='both',
    #    bottom=False,
    #    left=False,
    #    right=False,
    #    top=False)
    #ax_big.grid(False)
    #############

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

    multi_parser = subp.add_parser("multi")
    multi_parser.set_defaults(func=plot_multi)
    multi_parser.add_argument('src_dirs', nargs='*')

    ping_parser = subp.add_parser("ping")
    ping_parser.set_defaults(func=plot_ping)
    ping_parser.add_argument('src_dirs', nargs='*')

    set_pubfig()

    args = parser.parse_args()
    args.func(args)
