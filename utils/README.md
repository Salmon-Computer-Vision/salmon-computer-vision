# Utility Tools

## Setup SSH Reverse Tunnel

### Server

Create a new user solely for SSH tunnels/proxying.
```bash
sudo useradd tunnel
```

Create a group and add the new user:
```bash
sudo groupadd revtunnel
sudo usermod -aG revtunnel tunnel
```

Login to tunnel user and generate a new SSH key with no passphrase:
```bash
sudo su tunnel
ssh-keygen -t rsa -b 4096 -f ~/.ssh/revtunnel_id_rsa
```

Add the `revtunnel_id_rsa.pub` public key to `~/.ssh/authorized_keys`.

Put the contents of `reverse_tunnel.conf` to the bottom of `/etc/ssh/sshd_config`.
This prevents the usage of that unsecure SSH key to login to the shell or local tunneling.

### Client

Copy the SSH key `/home/tunnel/.ssh/revtunnel_id_rsa*` to the client's `~/.ssh/`.

Copy `ssh-home-tunnel.service` to the client's `/etc/systemd/system/`.

Edit the service file as appropriate, changing the user to `tunnel` and the address + port. Change
the local port default `36000` to an open port on your ***server***.

Enable and run the service:
```bash
sudo systemctl enable ssh-home-tunnel
sudo systemctl start ssh-home-tunnel
```

Then, you should be able to SSH to the client from the server as follows:
```bash
ssh client@localhost -p 36000
```

## Labels

If there are new labels, first, manually convert the XML \<labels\> in the `annotation.xml` file to JSON. Copy
it to `labels.json` Then, run

```bash
./jq-labels.sh labels.json > labels-converted.json
```

This creates the labels required to create CVAT tasks.

```bash
./make_cvat_tasks.sh path/to/cvat/cli.py "user:${pass-env}" localhost path/to/labels.json path/to/annotations share_path
```

Creates tasks on CVAT instance and uploads/matches annotations to their respective videos on the share path.

```bash
./dump_cvat.sh path/to/cvat/cli.py "user:${pass-env}" localhost <start-task-id> <last-task-id> dest/dir
./merge_datum.sh user "${pass-env}" source/dump/annotations filter/dir dest/dir
./convert_tf.sh source/datumaro dest/dir
```

## Dataset Creation Script

***Create an empty project with the correct labels as `empty_proj` in the current directory.***

Exports MOT and YOLO datasets based on CSV file:
```bash
./datum_create_dataset.py -j 4 [--export-off] [--format yolo] --anno-path annos --proj-path datum_proj --transform-path datum_proj_transform --export-path export /mnt/disk5tb/salmon_anno_bear_creek_123.csv
```

The CSV file must be of format:
```
filename,vid_path,anno_path
07-15-2020 15-51-08 M Left Bank Underwater,/path/to/vids/07-15-2020 15-51-08 M Left Bank Underwater.m4v,/path/to/annos/07-15-2020_15-51-08_M_Left_Bank_Underwater.zip
...
```

Use the following script to consolidate the YOLO dataset:
```
./yolo_combine.py path/to/export_yolo
```

Conforms split to export if split has changed
```bash
./conform_seqs_to_splits.sh datum_proj_merged_train_split/ export_yolo/
```

Converts a YOLOv5 dataset to YOLOv6 through symlinks, meaning do not delete the YOLOv5 dataset.
```bash
./symlink_yolov5_to_yolov6.sh export_yolo/ export_yolov6
```

For MOT (mot\_seq\_gt), you must put the `train`, `valid`, and `test` folders into a new `images` folder,
update the folder in the script `gen_labels_MOT.py`, and then run `python3 gen_labels_MOT.py`.
