# Batch Upload

This will create a cross-platform executable for offline sites that will batch
upload the data offsite.

## Windows Requirements

You need to install [*Build Tools for Visual Studio 2019 or
later*](https://visualstudio.microsoft.com/downloads/?q=build+tools) for
pyoxidizer to properly build the program into an exe.

## Build

Install pyoxidizer
```
python3 -m pip install pyoxidizer==0.24.0
```

Install wget:
```
sudo apt update && sudo apt install wget
```

Move to this folder:
```bash
cd utils/batch-upload
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

Make sure you download the correct one for the OS that is building the
executable.

Unzip the file and *rename* the extracted folder to `rclone-install`.

You can create an `rclone.conf` file in two ways. One by following the steps
from running `rclone config` on the host machine and finding `rclone.conf` in
`~/.config/rclone`. You can also simply use the following template for AWS S3:

```
# rclone.conf
[aws]
type = s3
provider = AWS
access_key_id = <access_key_ID>
secret_access_key = <access_key_secret>
region = <region_tag>
location_constraint = <region_constraint_tag>
acl = private
```

`region` and `location_constraint` are AWS region tags such as 

Add `.env` file of the syncing services and `rclone.conf` file to this folder:
```
cp ../pi/services/.env .
cp ~/.config/rclone/rclone.conf .
```

However, the `.env` and `rclone.conf` files can be swapped without rebuilding
the program by putting them adjacent to the executable file.

Build and package the program
```
# Linux and Mac
pyoxidizer build --release
# Windows
pyoxidizer build --var windows "" --release
```

Executable installs are in the folder `build`.

You can build and run the program with debugging by running the following:
```
# Linux and Mac
pyoxidizer run
# Windows
pyoxidizer run --var windows ""
```

Repeat these steps for other desired OSes and place them with
the file structure as follows:
```
batch-upload/
├─ batch-upload-linux-amd64/
   ├─ batch_upload
   ├─ ...
├─ batch-upload-windows-amd64/
   ├─ batch_upload.exe
   ├─ ...
├─ batch-upload-mac-amd64/
   ├─ batch_upload
   ├─ ...
```

This `batch-upload` folder must be placed in the harddrive adjacent to the data
ORGID folder to be uploaded.

Run the executables within the same folder as such:
```
# Linux
cd batch-upload/batch-upload-amd-linux
./batch_upload
```
