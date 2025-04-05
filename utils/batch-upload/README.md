Install pyoxidizer
```
python3 -m pip install pyoxidizer==0.24.0
```

Add `.env` file of the syncing services and `rclone.conf` file to here:
```
cp ../pi/services/.env .
cp ~/.config/rclone/rclone.conf .
```

```
pyoxidizer build
```

Executable installs are in the folder build.
