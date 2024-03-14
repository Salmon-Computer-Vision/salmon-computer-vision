#!/bin/bash

# Check if an input argument (directory) is provided
if [ $# -eq 0 ]; then
    echo "Usage: $0 <directory>"
    exit 1
fi

# Specify the directory to search in
search_dir="$1"

# Define the function to process each file
process_file() {
    file="$1"
    echo "Processing $file"
    temp_file=$(mktemp)

    while read -r line; do
        new_line=$(echo "$line" | awk '{
            for (i=1; i<=NF; i++) {
                if (i > NF-4) {
                    printf (i<NF ? "%s " : "%s\n"), ($i > 1.0 ? "1.0" : $i)
                } else {
                    printf (i<NF ? "%s " : "%s\n"), $i
                }
            }
        }')
        echo "$new_line" >> "$temp_file"
    done < "$file"
    
    mv "$temp_file" "$file"
}

export -f process_file

# Find all .txt files excluding train.txt, val.txt, and test.txt and process them in parallel
find "$search_dir" -type f -name "*.txt" ! -name "train.txt" ! -name "val.txt" ! -name "test.txt" -print0 | xargs -0 -I {} -P 32 bash -c 'process_file "$@"' _ {}

