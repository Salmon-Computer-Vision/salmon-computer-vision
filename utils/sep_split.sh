#!/usr/bin/env bash
set -e

# This script aims to separate the split json files into their own datumaro folders for mot_seq_gt exporting

split_dir=$1

create_config() {
    name=$1
    dir=$2

    cat > "${dir}/config.xml" << EOF
    format_version: 1
    models: {}
    project_name: ${name}
    subsets: []
    EOF
}

anno="dataset/annotations"
datum_dir=".datumaro"
sep_dir="${split_dir}_sep"
train_dir="${sep_dir}/train"
val_dir="${sep_dir}/val"
test_dir="${sep_dir}/test"

# Making separate datumaro dirs for each split
mkdir -p "${train_dir}/${anno}" "${train_dir}/${datum_dir}"
mkdir -p "${val_dir}/${anno}" "${val_dir}/${datum_dir}"
mkdir -p "${test_dir}/${anno}" "${test_dir}/${datum_dir}"

cp "${split_dir}/${anno}/train*" "${train_dir}/${anno}/"
cp "${split_dir}/${anno}/val*" "${val_dir}/${anno}/"
cp "${split_dir}/${anno}/test*" "${test_dir}/${anno}/"

create_config train "${train_dir}"
create_config val "${val_dir}"
create_config test "${test_dir}"
