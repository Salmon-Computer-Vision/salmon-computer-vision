#!/usr/bin/env bash
set -ex

rivers=(bear koeye kwawka kitwanga)

datasets=("test" "val" "train")
#datasets=("test")

label_file=../../2023_combined_salmon.yaml
div_num=19 # 19 -> 5%, 99 -> 1%

for river in "${rivers[@]}"; do
    echo "Starting $river river processing"
    if [[ "$river" == "kwakwa" || "$river" == "koeye" ]]; then
        input_folder=/mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2024-03-01/
        input_empty_folder=/mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2023_batch
    else
        input_folder=$(find /mnt/ayumissd4tb/masamim/ -maxdepth 1 | grep "salm_dataset_${river}_*")
        input_empty_folder="$input_folder"
    fi

    for dataset in "${datasets[@]}"; do
        echo ""
        echo "Processing $dataset"
        out_folder=/mnt/ayumissd4tb/masamim/salm_dataset8010_yolo_${river}_2023/$dataset
        out_empty_folder=/mnt/ayumissd4tb/masamim/salm_dataset8010_yolo_empty_${river}_2023/$dataset
        set_file=$(find ../../train_splits -maxdepth 1  | grep ${dataset}_${river}_*)

        python3 ../process_cvat_xml.py -f datumaro -o yolo --save-media --set-file "$set_file" "${input_folder}" "$out_folder" "$label_file"

        num_items=$(find "$out_folder" \( -name "*.png" -o -name "*.jpg" \) | wc -l)
        num_seqs=$(find "$out_folder" -name 'obj.data' | wc -l)
        num_empty=$((${num_items} / $div_num / ${num_seqs} + 1))

        echo "Will get ${num_empty} empty frames from each seq"

        
        if [[ "$river" == "kwakwa" || "$river" == "koeye" ]]; then
            python3 ../process_cvat_xml.py --no-filter -o yolo --save-media --empty-only --num-empty $num_empty --set-file "$set_file" --anno-name output.xml ../../DDD_annos/DDD\ UPLOAD "$out_empty_folder" "$label_file"
        fi

        python3 ../process_cvat_xml.py --no-filter -f datumaro -o yolo --save-media --empty-only --num-empty $num_empty --set-file "$set_file" --anno-name default.json "$input_empty_folder" "$out_empty_folder" "$label_file"
    done
done
