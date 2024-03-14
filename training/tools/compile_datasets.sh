#!/usr/bin/env bash
set -ex

datasets=("test" "val" "train")
#datasets=("test")

river=kwakwa
input_folder=/mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2024-03-01/
label_file=../../2023_combined_salmon.yaml
div_num=19 # 19 -> 5%, 99 -> 1%
for dataset in "${datasets[@]}"; do
    echo ""
    echo "Processing $dataset"
    out_folder=/mnt/ayumissd4tb/masamim/salm_dataset_yolo_${river}_2023/$dataset
    out_empty_folder=/mnt/ayumissd4tb/masamim/salm_dataset_yolo_empty_${river}_2023/$dataset
    set_file=../../train_splits/${dataset}_${river}_2023.csv

    python3 ../process_cvat_xml.py -f datumaro -o yolo --save-media --set-file "$set_file" "${input_folder}" "$out_folder" "$label_file"
    python3 ../process_cvat_xml.py --workers 1 -f datumaro -o yolo --save-media --set-file "$set_file" "${input_folder}" "$out_folder" "$label_file"

    num_items=$(find "$out_folder" -name '*.png' | wc -l)
    num_seqs=$(find "$out_folder" -name 'obj.data' | wc -l)
    num_empty=$((${num_items} / $div_num / ${num_seqs} + 1))

    echo "Will get ${num_empty} empty frames from each seq"

    python3 ../process_cvat_xml.py --workers 1 --no-filter -o yolo --save-media --empty-only --num-empty $num_empty --set-file "$set_file" --anno-name output.xml ../../DDD_annos/DDD\ UPLOAD "$out_empty_folder" "$label_file"

    python3 ../process_cvat_xml.py --workers 1 --no-filter -f datumaro -o yolo --save-media --empty-only --num-empty $num_empty --set-file "$set_file" --anno-name default.json /mnt/ayumissd4tb/masamim/salm_dataset_koeye_kwakwa_2023_batch "$out_empty_folder" "$label_file"
done
