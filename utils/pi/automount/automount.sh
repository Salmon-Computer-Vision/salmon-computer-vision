#!/usr/bin/env bash
ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"

FS_TYPE=$(blkid -s TYPE -o value "$DEVICE")

case "${ACTION}" in
    add)
        if [ "$FS_TYPE" = "ext4" ]; then
            /usr/bin/mount -t ext4 -o defaults $DEVICE /media/hdd
        else
            /usr/bin/mount -o user,auto,fmask=0000,dmask=0000 $DEVICE /media/hdd
        fi
        /bin/systemctl restart smbd || true
        ;;
    remove)
        /bin/umount /media/hdd
        ;;
esac

