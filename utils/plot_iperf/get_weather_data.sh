#!/usr/bin/env bash

dest_dir=weather
station_id=888  # 888 - Vancouver Harbour CS
mkdir -p "$dest_dir"

download_data() {
    dest_dir=$1
    station_id=$2
    year=$3
    month=$4
    day=$5

    month_f=$(printf "%02d" $month)
    day_f=$(printf "%02d" $day)

    wget -O "${dest_dir}/climate_hourly_BC_${year}-${month_f}-${day_f}.csv"  --content-disposition "https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=${station_id}&Year=${year}&Month=${month}&Day=${day}&timeframe=1&submit= Download+Data"
}

export -f download_data

for year in `seq 2022 2022`; do
    for month in `seq 1 7`; do
        for day in `seq 1 1`; do # Hourly measures give entire month of data
            sem -j 4  download_data "$dest_dir" "$station_id" "$year" "$month" "$day"
        done
    done
done

sem --wait
