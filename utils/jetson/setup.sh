#!/usr/bin/env bash

# Pass SSH deploy keys first!

sudo apt-get update && sudo apt-get upgrade -y

# Set text-only GUI for lower memory usage
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true dpkg-reconfigure lightdm
echo set shared/default-x-display-manager lightdm | debconf-communicate

# Maximize device performance
sudo nvpmodel -m 0
sudo jetson_clocks

sudo apt-get install -y git tmux

git clone --depth 1 https://github.com/Salmon-Computer-Vision/ByteTrack.git ~/ByteTrack

# Reboot to finish setup
