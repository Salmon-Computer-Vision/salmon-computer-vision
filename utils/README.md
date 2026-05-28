# Utils

## Troubleshooting

### Network not connecting even with correct IP address

This is likely due to the device resetting back to factory date/time settings
if it does not have a RTC (Real-Time Clock) battery which can mess up the
software that requires network connectivity.

Open the terminal through CTRL+ALT+T if not connected through SSH.

Check if the date is correct:

```bash
date
```

If it's not correct and set to 1970 or 2000, run the following commands to fix it.

First, turn on NTP which will update the date/time through the Internet:
```
sudo timedatectl set-ntp true
```

You can set the date/time manually through this command:
```
sudo timedatectl set-time "YYYY-MM-DD HH:MM:SS"
```

If the device has an RTC battery, you can save the time into the hardware clock
like this:

```bash
sudo hwclock --systohc
```

An alternative if the device does not have an RTC battery is to use the
`fake-hwclock` service:

```bash
sudo apt update && sudo apt install fake-hwclock
```

Enable and start the service:
```bash
sudo systemctl enable fake-hwclock.service
sudo systemctl start fake-hwclock.service
```

This will periodically save the current time to a file and load it up upon
startup, so the device starts at a reasonable datetime for NTP to set the
correct time or for offline work to still work without an incredibly old
timestamp.

### Cannot clone the SD card as the target SD card is a different manufacturer

Different manufacturers of SD cards have slightly different sizes, which makes
cloning SD cards of the same size difficult across different manufacturers' SD
cards.

This is a step-by-step to backup the source SD card as an .img file, shrink the
partition slightly using a script, and then write the .img file to the new SD
card. You’ll also need at least 256 GB of extra space on your PC to hold the
backup.

There’s this [YouTube video that shows this
step-by-step](https://youtu.be/5pdgO3Ncl6k?si=pkhHyAow0aLVPcds), but below the
steps are outlined and instead of using a virtual machine as the video says,
you can install WSL (Windows Subsystem for Linux) as per the steps below.

[Here is another step-by-step in text
format.](https://www.reddit.com/r/raspberry_pi/comments/1kqtk3c/windows_11_software_to_create_backup_img_from_rpi/)

Here are the steps:

On Windows, use Win32 Disk Imager to backup the SD card as an .img file.
Install [link here](https://sourceforge.net/projects/win32diskimager/)

You can follow the YouTube tutorial to image the SD card into an .img file.

Install WSL which is a linux based commandline tool that lives inside Windows.
1.	Hit the windows key to open the start menu
2.	Type in “Powershell” to search
3.	Right click “Windows Powershell” and hit “Run as administrator”
4.	In the terminal that pops up, type in `wsl --install Ubuntu`
5.	Follow the instructions. You may need to restart your PC after it installs
[More info here if needed](https://learn.microsoft.com/en-us/windows/wsl/install)

Go to where you kept the .img file.

Click on the address bar of your folders window and type in `bash` then press Enter which will open a bash terminal.

Copy and paste the following to download pishrink:

```bash
wget https://raw.githubusercontent.com/Drewsif/PiShrink/refs/heads/master/pishrink.sh -O pishrink.sh
```

Run this command to shrink the img file:

```bash
sudo bash pishrink.sh -vz name_of_img_file.img
```

Finally, use BalenaEtcher to flash the `.gz` zipped file to the new SD card. You can
zip it yourself using 7-zip as the video describes, but pishrink can zip with
the `-z` flag itself which was used in the above command.

### Harddrive disconnects

This issue happens often with the Marlin Boxes where the harddrive would
disconnect and can be temporarily brought back by restarting the
microcontroller.

Someone needs to be physically on-site to replug the harddrive. It may be
simply turning the orientation of the cable upside down and checking if the
waterproof port is properly screwed in.

Once the harddrive plugged in and mounted, run the following to check the harddrive.
```bash
lsusb -t
```

Look for the one that says `Class=Mass Storage` and check the number at the
end. It should say either 5000M or 10000M when it is mounted properly. If not,
try a different orientation or connection method such as through the USB-A port
not using the waterproof cables.

### Slowness in SD Card-powered microcontrollers

If a microcontroller that relies on SD cards become slow, this could be due to
SD card deterioration and should be replaced. SD cards are not ideal for heavy
production use products and should be switched to an M.2 SSD if the
microcontroller allows.

One step, however, that could fix this issue temporarily is by removing
unnecessary docker images and rebooting.

Check docker images:
```bash
docker images
```

Remove docker image:
```
docker rmi <image_tag>
```

Reboot:
```bash
sudo reboot
```

Another step is to have the system check the filesystem after boot:

```bash
sudo tune2fs -c 1 /dev/sdX
```
This will have the filesystem be checked after every boot.

Reboot
```bash
sudo reboot
```

Set to after 3 boots
```bash
sudo tune2fs -c 3 /dev/sdX
```


## [Incomplete] Quick Deploy Services Script

***Only works after all devices are properly setup***

The bash script `deploy-system.sh` can be used to automatically deploy the services
to all of your remote devices. Simply create and fill in a `deploy-vars.sh` file with
the following:

```bash
#!/usr/bin/env bash
# utils/deploy-vars.sh
MAX_DEVICES=2

sites=(
    hirmd-koeye
    # Other sites here...
)

# Define an array of systems, each with its own image and environment file
declare -A systems=(
    ["jetsonorin"]="<host>/salmoncounter:latest-jetson-jetpack6"
    ["jetson"]="<host>/salmoncounter:latest-jetson-jetpack4"
    ["pi"]="<host>/salmonmd:latest-bookworm"
)
```

Run the script as such in this directory
```bash
./deploy-system.sh
```
