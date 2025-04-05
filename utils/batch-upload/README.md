# Batch Upload

This will create a cross-platform executable for offline sites that will batch
upload the data offsite.

Install pyoxidizer
```
python3 -m pip install pyoxidizer==0.24.0
```

Install wget:
```
sudo apt update && sudo apt install wget
```

[Download the rclone executable](https://rclone.org/downloads/). You can use
the following URLs for Intel/AMD 64-bit or go to the website for your exact
distribution:

```
# Linux
wget https://downloads.rclone.org/rclone-current-linux-amd64.zip
# Windows
wget https://downloads.rclone.org/rclone-current-windows-amd64.zip
# macOS
wget https://downloads.rclone.org/rclone-current-osx-amd64.zip
```

Make sure you download the correct one for your OS.

Unzip the file and *rename* the extracted folder to `rclone-install`.

Add `.env` file of the syncing services and `rclone.conf` file to here:
```
cp ../pi/services/.env .
cp ~/.config/rclone/rclone.conf .
```

Build and package the program
```
pyoxidizer build
```

Executable installs are in the folder build.
