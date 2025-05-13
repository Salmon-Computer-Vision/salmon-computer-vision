# Jetson Nano Setup

The Jetson Nano is mainly used to process motion detected video clips and
generate object detection tracks and salmon species counts using the trained
deep learning model. The Jetson Nano will likely use all of the RAM it has
available to do this, and due to the RAM being shared between the CPU and GPU,
it cannot perform too many other tasks other than deep learning processing.

If you have multiple devices that require setting up, you can perform this
setup once on one device and then clone the SD card for every other device to
save time.

! Remember to update the [hostname appropriately and restart Tailscale](#Rename-the-machine-Hostname).

## Setup

Docker compose is needed to run the services with specific settings that allow
remote access and process video clips.

After SSHing to or opening the terminal on the Jetson Nano, install
docker-compose:

```
python3 -m pip install -U pip
python3 -m pip install docker-compose
sudo apt update && sudo apt install tmux
```

Add the user to the docker group:
```bash
sudo usermod -aG docker <username>
```

## Tailscale

Tailscale is a remote connection software. Once setup, any client that's also
running on the same Tailscale network will be able to access this device
through any network including SSH. This can be fine-tuned to only allow certain
clients or tag a group of clients on the Tailscale console.

We use tailscale to remotely access the devices at sites with network
connectivity for troubleshooting and updating the docker images if necessary.

First, create a [Tailscale account](https://tailscale.com/). Then, setup your
tailscale with Access controls for the tag `salmon-project` to prevent reverse
access to client devices for security.

This can look like as follows:

```
{
    // // Declare static groups of users. Use autogroups for all users or users with a specific role.
	"groups": {
        "group:admin": ["admin@example.com"],
		"group:salmon-project": [
            "email@example.com",
		],
	},

    
	// Define the tags which can be applied to devices and by which users.
	"tagOwners": {
		"tag:salmon-project":        ["group:admin"],
		"tag:shared-public-devices": ["group:admin"],
	},

	// Define access control lists for users, groups, autogroups, tags,
	// Tailscale IP addresses, and subnet ranges.
    "acls": [
		// Allow all connections.
		// Comment this section out if you want to define specific restrictions.
		{
			"action": "accept",
			"src":    ["autogroup:member"],
			"dst":    ["autogroup:self:*"],
		},
		{
			"action": "accept",
			"src":    ["group:admin", "group:salmon-project"],
			"dst":    ["tag:salmon-project:*"],
		},
	],
}
```

This sets the `salmon-project` tag to prevent reverse connections through
Tailscale for security reasons but would allow a host machine that installs
tailscale manually to connect to them.

Generate a Tailscale OAuth client key in the settings with "Auth Keys" Read and
Write permissions with the `salmon-project` tag.

Clone this repo on the target device if not already:

```bash
git clone --depth 1 https://github.com/Salmon-Computer-Vision/salmon-computer-vision.git
```

Move to this directory:
```bash
cd salmon-computer-vision/utils/jetson
```

Create an `.env` file in this folder with your tailscale auth key:

```
# utils/jetson/.env
YOURKEY=<auth key>
```

Run the following to start up Tailscale:
```bash
docker-compose up -d
```

This creates a docker container described in `docker-compose.yaml` that adds the
`salmon-project` tag to connect to the tailscale account described by the OAuth
client key.

You should then be able to remote access this device on other devices that are
also running tailscale. You may need to [install
manually](https://tailscale.com/download) on your client devices as the OAuth
key only allows one-way access.

Then, the following should be possible on the client device:
```bash
ssh <user>@<jetson-hostname>
```

The following will shutdown tailscale, however, **do not do this if the only
connection is tailscale**:

```
docker-compose down
```

This may be fine if there are other local area devices you can access that can
access this device.

### Rename the machine Hostname

Update the hostname of the device if not already to change the name on the admin console:
```
sudo hostnamectl set-hostname <new-hostname>
```

***!! Note to facilitate downstream tasks, we will standardize the hostnames as such***
```
<ORGID>-<river-name>-<device>-<num>
```
`<device>` could be `pi` or `jetson`.

For example,
```
KXSA-kwakwa-jetson-0
```

If this is run after Tailscale is already up, reboot the machine and do the following:

First, delete the Tailscale status folder (the folder name can be different depending on the YAML file)
```
sudo rm tailscale-oauth/ -r
```
***!!!*** Then, you ***MUST*** run the following command under the ***Tmux environment***, otherwise, you are likely to lose the SSH remote connection permanently.
```bash
tmux
docker-compose down && docker-compose up -d
```

### Updating Tailscale

If there is an urgent security update for tailscale, you can update tailscale
as follows:

```
docker pull tailscale/tailscale:latest
```
Then restart the docker-compose as above in the Tmux environment. 


### Samba Share

This setup will allow access to the harddrive for the video data is not
attached to this device.

To automatically mount the NFS share of the harddrive attached to a different
device install NFS client and autofs:

```bash
sudo apt update && sudo apt install cifs-utils autofs
```

Create mount dir:
```bash
sudo mkdir -p /media/hdd
```

Edit `/etc/auto.master`:
```bash
sudoedit /etc/auto.master
```

Add the following to the bottom:
```bash
/- /etc/auto_static.smb --timeout=60
```

Create a new file:
```bash
sudoedit /etc/auto_static.smb
```

with the following:
```bash
/media/hdd  -fstype=cifs,rw,guest,uid=1000,gid=1000,file_mode=0777,dir_mode=0777  ://<raspi_ip>/HDD
```
Replace `<raspi_ip>` with the static IP address of the Raspberry Pi that is mounting
the external drive.

\[!\] Note if the device's uid/gid is different, change it the current device's
uid/gid. Run the command `id` to view. The filesystem may be slower than normal
if this is not done correctly.

Restart and enable the autofs service:
```bash
sudo systemctl restart autofs
sudo systemctl enable autofs
```

Check if it is properly mounted by listing or running `df`:
```bash
ls /media/hdd
df -h
```

## SalmonMD

The Salmon Motion Detector runs simple background subtraction and erosion algorithms
to cut up continuous video into more manageable clips. Depending on RAM or resources usage,
this may not be able to run simultaneously with the salmon counting software and deep learning
model, requiring a separate device such as a raspberry pi to perform the motion detection.

See the [`salmonmd` folder](salmonmd) for step-by-step instructions.

## Salmon Counter

The Salmon Counter runs the deep learning model to automatically detect fish
species, track their position, and count each species.

See the [`salmoncount` folder's README](salmoncount) for step-by-step
instructions.

## Setup Static IP

Jetson Nano by default uses Network Manager to provision its networking.

Use `nm-connection-editor` or the CLI to edit the IPv4 static IP.

```bash
sudo nm-connection-editor
```

If you are SSHing into the device, use the `-X` flag to relay the window
to your host machine:

```bash
ssh -X <jetson_user>@<jetson_ip>
```

By default Starlink uses the following:
* Gateway: 192.168.1.1
* DNS: 192.168.1.1
* Netmask: 255.255.255.0 OR 24

Here are the series of commands with `nmcli`:
```bash
sudo nmcli con add con-name eth0 ifname eth0 type ethernet autoconnect yes
sudo nmcli con mod eth0 ipv4.addresses 192.168.1.20/24
sudo nmcli con mod eth0 ipv4.gateway 192.168.1.1
sudo nmcli con mod eth0 ipv4.dns 192.168.1.1,1.1.1.1
sudo nmcli con mod eth0 ipv4.method manual
sudo nmcli con up eth0
```
Replace `192.168.1.20` with your preferred address.
Check `nmcli con show` to find the correct network interface if it's not `eth0`.

## Barlus Camera Caveats

PTZ usage works by inputting the numeric value in the box and pressing the "Call" button to incur the
described function.

For example, set the value as 250 and click "Call" to save the lighting configuration.
