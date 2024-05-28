#!/usr/bin/env bash
ACTION=$1
DEVBASE=$2
DEVICE="/dev/${DEVBASE}"

case "${ACTION}" in
    add)
        /usr/bin/mount -o user,auto,fmask=0000,dmask=0000 $DEVICE /media/nfs/hdd
        /sbin/exportfs -ra
        /bin/systemctl restart nfs-kernel-server
        ;;
    remove)
        /bin/umount /media/nfs/hdd
        ;;
esac

