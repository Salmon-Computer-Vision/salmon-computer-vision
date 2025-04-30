# Syncing Data

This uses rclone to sync to AWS

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

