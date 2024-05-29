# Automounting with `usbmount`

Install `usbmount` to auto mount any USB devices that are plugged in:
```bash
sudo apt install usbmount
```

USB devices should be automatically mounted to `/media/usb[0-7]`.

If auto mounting NTFS filesystems is desired [this link should
help](https://raspberrypi.stackexchange.com/questions/41959/automount-various-usb-stick-file-systems-on-jessie-lite).
```bash
sudoedit /etc/usbmount/usbmount.conf
```

Search for `FILESYSTEMS` and add `ntfs`, `fuseblk`, and `exfat`:
```
FILESYSTEMS="ntfs fuseblk ext2 ext3 ext4 hfsplus exfat"
```
If needed, you can add `vfat`, though, likely only small USB thumb drives will use that file system.

Add options required to access the mounted folders:
```
FS_MOUNTOPTIONS="-fstype=ntfs-3g,nls=utf8,umask=007,gid=46 -fstype=fuseblk,nls=utf8,umask=007,gid=46 -fstype=exfat,uid=1000,gid=1000,umask=000"
```
Check the UID of your desired user through the `/etc/group` file.

```bash
sudoedit /etc/udev/rules.d/usbmount.rules
```
Add the following rules:
```
KERNEL=="sd*", DRIVERS=="sbp2",         ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="sd*", SUBSYSTEMS=="usb",       ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="ub*", SUBSYSTEMS=="usb",       ACTION=="add",  PROGRAM="/bin/systemd-escape -p --template=usbmount@.service $env{DEVNAME}", ENV{SYSTEMD_WANTS}+="%c"
KERNEL=="sd*",                          ACTION=="remove",       RUN+="/usr/share/usbmount/usbmount remove"
KERNEL=="ub*",                          ACTION=="remove",       RUN+="/usr/share/usbmount/usbmount remove"
```

Then, create a systemd service:
```bash
sudoedit /etc/systemd/system/usbmount@.service
```
With the following contents:
```
[Unit]
BindTo=%i.device
After=%i.device

[Service]
Type=oneshot
TimeoutStartSec=0
Environment=DEVNAME=%I
ExecStart=/usr/share/usbmount/usbmount add
RemainAfterExit=yes
```

```bash
sudo systemctl edit systemd-udevd
```
Put the following:
```
[Service]
PrivateMounts=no
```

Then, reboot.

Create a new user to restrict ssh key usage:
- Setup a new user (eg. `lockeduser`)
- Create and give new user the `sshfs` group
- Put the contents of `sshfs.conf` into the bottom of `/etc/ssh/sshd_config`
- Add the contents of `revtunnel_id_rsa.pub` to the new user's `/home/lockeduser/.ssh/authorized_keys`

