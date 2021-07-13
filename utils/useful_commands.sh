# Disable GUI on boot
sudo systemctl set-default multi-user.target
# Renable GUI
#sudo systemctl set-default graphical.target

# Jetson Nano Only
# Use max power
sudo nvpmodel -m 0
sudo jetson_clocks
