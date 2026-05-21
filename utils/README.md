# Utils

## Troubleshooting

### Network not connecting

This is likely due to the device resetting back to factory date/time settings
if it does not have a RTC (Real-Time Clock) battery which can mess up the
software that requires network connectivity.

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
