# Utils

## Quick Deploy Services Script

***Only works after all devices are properly setup***

The bash script `deploy-system.sh` can be used to automatically deploy the services
to all of your remote devices. Simply create and fill in a `deploy-vars.sh` file with
the following:

```bash
#!/usr/bin/env bash
# utils/deploy-vars.sh
MAX_DEVICES=2

sites=(
    hirmd-koeye
    # Other sites here...
)

# Define an array of systems, each with its own image and environment file
declare -A systems=(
    ["jetsonorin"]="<host>/salmoncounter:latest-jetson-jetpack6"
    ["jetson"]="<host>/salmoncounter:latest-jetson-jetpack4"
    ["pi"]="<host>/salmonmd:latest-bookworm"
)
```

Run the script as such in this directory
```bash
./deploy-system.sh
```
