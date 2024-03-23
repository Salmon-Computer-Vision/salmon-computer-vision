#!/bin/bash
set -e

inputs=(
#/mnt/ayumissd4tb/masamim/salm_dataset8010_datumaro/salm_dataset8010_datumaro_koeye_2023/test
#/mnt/ayumissd4tb/masamim/salm_dataset8010_datumaro/salm_dataset8010_datumaro_kwakwa_2023/test
#/mnt/ayumissd4tb/masamim/salm_dataset8010_datumaro/salm_dataset8010_datumaro_koeye_2023
#/mnt/ayumissd4tb/masamim/salm_dataset8010_datumaro/salm_dataset8010_datumaro_kwakwa_2023
"/mnt/ayumissd4tb/masamim/Salmon_Videos/Koeye 2023 videos"
"/mnt/ayumissd4tb/masamim/Salmon_Videos/Kwakwa Video 2023"
)

input_format="video" # video|datumaro
output_folder="model_full_counts"

# Define the base name for the split files
base_split_name="split_list_"

declare -A models=( ["KiBeKoKw"]="33" ["KoKw"]="35" )

model="KoKw"
#for model in "${!models[@]}"; do
    echo "Running $model"
    for input_folder in "${inputs[@]}"; do
        echo "Testing on $input_folder"

        #parent_dir=$(dirname "$input_folder")
        parent_dir="$input_folder"
        name=$(basename "$parent_dir")

        if [[ "$input_format" == "datumaro" ]]; then
            # Step 1: Find all default.json files and save the list to a temporary file
            find "$input_folder" -name 'default.json' > all_paths.txt
        elif [[ "$input_format" == "video" ]]; then
            echo ""
            #find "$input_folder" -name '*.mp4' > all_paths.txt
        fi

        # Step 2: Split this list into 4 separate text files
        total_lines=$(wc -l < all_paths.txt)
        ((lines_per_file = (total_lines + 3) / 4)) # Plus 3 for rounding up division

        # Splitting the file. Adding a suffix to easily identify them.
        split -l "$lines_per_file" all_paths.txt "${base_split_name}"

        # Collect the split files into an array
        split_files=(${base_split_name}*)

        # Step 3: Run the Python script in parallel for each split file, with incremented device number
        for i in "${!split_files[@]}"; do
            anno_list_path="${split_files[$i]}"
            csv_output_path="${output_folder}/full_${model}_${name}_${i}.csv"
            weights_path="runs/detect/train${models[${model}]}/weights/best.pt" 

            # Run the Python script in the background
            python3 tools/count_test.py "$input_folder" "$anno_list_path" "$csv_output_path" -f $input_format --weights "$weights_path" --device "$i" &
        done

        # Wait for all background jobs to finish
        wait

        rm ${base_split_name}*

        echo "All processes have completed."

    done
#done
