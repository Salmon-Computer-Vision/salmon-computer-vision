#!/usr/bin/env bash
source deploy-vars.sh

# Loop over all the sites
for site in "${sites[@]}"; do
    # Loop over the systems
    for system in "${!systems[@]}"; do
        for ((device_id=0; device_id<MAX_DEVICES; device_id++)); do
            context="${site}-${system}-${device_id}"
            service_dir="jetson/salmoncount"
            if [[ $system == "pi" ]]; then
                service_dir="pi/services"
            fi

            echo "Deploying to context: ${context} with service directory: ${service_dir}"

            # Navigate to the correct service directory
            cd "$service_dir" || exit

            # Pull the latest image for the respective system
            docker --context "$context" pull "${systems[$system]}"

            # Bring up the services with appropriate environment files
            docker --context "$context" compose --env-file .env --env-file ".env-${site}-${system}" up -d

            cd - > /dev/null
        done
    done
done
