# Syncing Data

This uses rclone to sync to AWS

- `syncing` uses rclone to copy and upload to the `aws` configuration only the motion detected videos and metadata
- `syncing-detects` is the same as `syncing` but only uploads the YOLO format with track ID detection `.txt` files
- `syncing-counts` is the same as `syncing` but only uploads the counts `.csv` files for each video

Create a `.env` file here with the following:
```
USERNAME=<device_username>
DRIVE=/media/hdd
ORGID=<ORGID>
SITE_NAME=<site_name>
BUCKET=<bucket_name>
```

Create or edit `~/.config/rclone/rclone.conf` and add the contents of
`rclone.conf` in this folder to it.

Start the syncing services with the following:
```
docker compose up -d
```

When updating, be sure to build the containers as some may be built at runtime:
```
docker compose build
```

This uses the latest `rclone` image, so if desired, one can update the image:
```
docker compose pull
docker compose up -d
```
