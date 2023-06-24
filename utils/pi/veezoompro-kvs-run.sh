#!/usr/bin/env bash
name=$1
stream_name=$2

contains() {
    [[ $1 =~ (^|[[:space:]])$2($|[[:space:]]) ]] && exit(0) || exit(1)
}

whitelist=(IPS)

for ip in $(nmap -n -sn 192.168.1.0/24 -oG - | awk '/Up$/{print $2}'); do
    if ! contains whitelist ip; then
        rtsp_url="rtsp://admin:admin@${ip}/1/2"
        /home/salmonpi/salmon-computer-vision/utils/pi/docker-kvs-run.sh $name "$rtsp_url" $stream_name
    fi
done
