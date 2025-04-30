# Jetson After Cloning Setup

- Update hostname and update tailscale name
- Update `/etc/hosts`
- Physically label the device with tape with the same hostname
- Update static IP if necessary
- Add device to healthchecks
- Mount samba share if necessary
- Update `.env` variables
- Check if the external drive is auto-mounted to `/media/hdd`
- Test on dev bucket
- Set for production
- Spin up services
- Turn off

After cloning/imaging the disk to a different device, these are the steps to
take to set it up for either a new site or another camera of the same site.

## Hostname

```
sudo hostnamectl set-hostname ORGID-sitename-jetsonnx-0
```

* `ORGID` is the organization ID that will be provided.
* `sitename` is usually the river name but can be different and will also be provided

* `jetsonnx` is the device ID usually depends on the type of device. Keep this
  the same if it's the Jetson Orin NX Supers

* Increment the number if there is another camera on the same site

For example, one hostname could be `HIRMD-koeye-jetson-0`. This is the hostname
of the organization with the ID HIRMD for the Koeye river. This one was a
normal Jetson Nano for the first camera of the weir.

Open a tmux session
```
tmux
```

Go to the jetson folder
```
cd salmon-computer-vision/utils/jetson
```

Remove the tailscale config folder
```
sudo rm -r tailscale-oauth/
```

Restart the tailscale service
```
docker compose down && docker compose up -d
```

If you are connecting to the device through tailscale, the terminal would freeze.
Open a new terminal and the device should come up as the new hostname on tailscale.

```
tailscale status
```

To prevent sudo warnings due to the new hostname, edit `/etc/hosts` with the
new hostname:

```
sudoedit /etc/hosts
```

It would helpful to use some labeling tape and place it on the device to label
it with the hostname to differentiate it visually with the other devices.

## Static IP



## Healthchecks.io

This is only useful for Internet-enabled sites as we can have the device send
healthcheck pings to healthchecks.io to make sure it is still running.

First, login to healthchecks.io and get an invite to the Salmon CV Project.

It is easier to clone one of the existing checks by clicking the three dots
on the right of one of them, going to the bottom and clicking "Create a Copy..."

Update the name to be same as the new hostname determined above and click "Copy URL."

Login or SSH back to the Jetson and open crontab:

```
crontab -e
```

And either replace the URL or add append this, updating the URL:

```
* * * * * curl -fsS -m 10 --retry 5 -o /dev/null https://hc-ping.com/<ping_url>
```

This will then send a ping every minute

Finally, adjust the schedule on healthchecks.io to how long the
Starlink/Internet connectivity is up using cron expressions, determining which
hours the Starlink should be on.

## Mount Samba Share

This is only necessary if this will not be the device the external harddisk/SSD
will be attached to such as it being the second device for a two camera system.


