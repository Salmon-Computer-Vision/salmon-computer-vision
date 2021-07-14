# Disable GUI on boot
sudo systemctl set-default multi-user.target
# Renable GUI
#sudo systemctl set-default graphical.target

# Jetson Nano Only
# Use max power
sudo nvpmodel -m 0
sudo jetson_clocks

# /etc/fstab
# sshfs#pi@raspberrypi.local:/media/usb0/ /mnt/pi-ssd fuse defaults,_netdev,allow_other,reconnect 0 0
# Must update `jetson-inference/docker/run.sh` at the bottom, remove 't' from '-it' and add '--name jetson'

# usbmount -- requires changing systemd-udevd service to "PrivateMounts=no"
# NTFS: https://raspberrypi.stackexchange.com/questions/41959/automount-various-usb-stick-file-systems-on-jessie-lite
