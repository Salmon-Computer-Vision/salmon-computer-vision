#!/usr/bin/env bash
ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"

case "${ACTION}" in
    add)
        /usr/bin/mount -o user,auto,fmask=0177,dmask=0077,uid=1002 $DEVICE /media/nfs/hdd
        /sbin/exportfs -ra
        /bin/systemctl restart nfs-kernel-server
        ;;
    remove)
        /usr/bin/umount /media/nfs/hdd
        ;;
esac

