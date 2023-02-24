#!/usr/bin/env bash

# Pass SSH deploy keys first!

# Set lower memory usage GUI
echo "/usr/sbin/lightdm" > /etc/X11/default-display-manager
DEBIAN_FRONTEND=noninteractive DEBCONF_NONINTERACTIVE_SEEN=true dpkg-reconfigure lightdm
echo set shared/default-x-display-manager lightdm | debconf-communicate

# Maximize device performance
sudo nvpmodel -m 0
sudo jetson_clocks

sudo apt-get install git
eval `ssh-agent -s`
ssh-add ~/.ssh/comp_vis_id_rsa
git clone --depth 1 git@github.com:Salmon-Computer-Vision/salmon-computer-vision.git
git clone --depth 1 https://github.com/Salmon-Computer-Vision/ByteTrack.git

# Reboot to finish setup
