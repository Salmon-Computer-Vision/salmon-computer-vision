#!/usr/bin/env bash

station_id=888  # 888 - Vancouver Harbour CS
dest_dir=weather
mkdir -p "$dest_dir"

for year in `seq 2022 2022`; do
    for month in `seq 2 2`; do
        for day in `seq 20 28`; do
            month_f=$(printf "%02d" $month)
            day_f=$(printf "%02d" $day)
            sem -j 4 wget -O "${dest_dir}/climate_hourly_BC_${year}-${month_f}-${day_f}.csv"  --content-disposition "https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID=${station_id}&Year=${year}&Month=${month}&Day=${day}&timeframe=1&submit= Download+Data"
        done
    done
done

sem --wait
