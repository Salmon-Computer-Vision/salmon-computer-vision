# Jetson Nano Setup

The Jetson Nano is mainly used to process motion detected video clips and
generate object detection tracks and salmon species counts using the trained
deep learning model. The Jetson Nano will likely use all of the RAM it has
available to do this, and due to the RAM being shared between the CPU and GPU,
it cannot perform too many other tasks other than deep learning processing.

## Docker compose

Docker compose is needed to run the services with specific settings that allow
remote access and process video clips.

After SSHing to or opening the terminal on the Jetson Nano, install
docker-compose:

```
python3 -m pip install -U pip
python3 -m pip install docker-compose
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

Generate a Tailscale OAuth client key in the settings with "Devices" read permissions
and the `salmon-project` tag.

Move to this directory:
```bash
cd utils/jetson
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

You should then be able to remote access this device on other devices that are
also running tailscale. You may need to [install
manually](https://tailscale.com/download) on your client devices.

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

**!! Note to facilitate downstream tasks, we will standardize the hostnames as such**
```
<ORG-ID>-<river-name>-<device>-<num>
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
```
docker-compose down && docker-compose up -d
```

### Update the Docker Tailscale
```
docker pull tailscale/tailscale:latest
```
Then restart the docker-compose as above in the Tmux environment. 

## Salmon Counter

See the [`salmoncount` folder's README](salmoncount) for more info.

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
Replace `192.168.1.20` with your perferred address.
Check `nmcli con show` to find the correct network interface if it's not `eth0`.

## Barlus Camera Caveats

PTZ usage works by inputting the numeric value in the box and pressing the "Call" button to incur the
described function.

For example, set the value as 250 and click "Call" to save the lighting configuration.
