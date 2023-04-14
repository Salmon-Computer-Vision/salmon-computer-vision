#!/usr/bin/env bash

export DEBIAN_FRONTEND=noninteractive
export DEBCONF_NONINTERACTIVE_SEEN=true 

sudo apt-get update && sudo apt-get upgrade -y -o Dpkg::Options::="--force-confnew"

# Do second round of upgrading
sudo apt-get update && sudo apt-get upgrade -y -o Dpkg::Options::="--force-confnew"

# Set text-only GUI for lower memory usage
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
dpkg-reconfigure lightdm
echo set shared/default-x-display-manager lightdm | debconf-communicate

# Maximize device performance
sudo nvpmodel -m 0
sudo jetson_clocks

sudo apt-get install -y git tmux sshfs

git clone --depth 1 https://github.com/Salmon-Computer-Vision/ByteTrack.git ~/ByteTrack
mkdir -p ~/ByteTrack/YOLOX_outputs/yolox_nano_salmon

sudo groupadd docker
sudo usermod -aG docker $USER

# Reboot to finish setup
