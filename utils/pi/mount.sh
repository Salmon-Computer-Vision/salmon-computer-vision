#!/usr/bin/env bash
ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"

case "${ACTION}" in
    add)
        /usr/bin/mount -o user,auto,fmask=0177,dmask=0077,uid=1002 $DEVICE /media/netlabmedia/hdd
        ;;
    remove)
        /usr/bin/umount /media/netlabmedia/hdd
        ;;
esac
