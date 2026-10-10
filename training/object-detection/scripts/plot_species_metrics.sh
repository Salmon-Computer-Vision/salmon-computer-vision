#!/usr/bin/env bash
# Show current species metrics, or compare selected experiment revisions.
# Usage:
#   scripts/plot_species_metrics.sh val hota
#   scripts/plot_species_metrics.sh test idf1 tracking-site-koeye tracking-site-tankeeah
#   scripts/plot_species_metrics.sh val count-compare
#   scripts/plot_species_metrics.sh val count-mae tracking-run1 tracking-run2
set -euo pipefail
if (( $# < 2 )); then
  echo "Usage: $0 {val|test} {hota|idf1|deta|assa|count-mae|count-compare} [DVC_REVISIONS...]" >&2
  exit 2
fi
split="$1"; kind="$2"; shift 2
case "$split" in val|test) ;; *) echo "Unknown split: $split" >&2; exit 2;; esac
folder="data/03_processed/tracking_eval"
case "$kind" in
  hota) target="$folder/${split}_tracking_per_species.csv"; field=HOTA; templ=config/plots/tracking_species_scores.vl.json; title="Species tracking HOTA: $split";;
  idf1) target="$folder/${split}_tracking_per_species.csv"; field=IDF1; templ=config/plots/tracking_species_scores.vl.json; title="Species tracking IDF1: $split";;
  deta) target="$folder/${split}_tracking_per_species.csv"; field=DetA; templ=config/plots/tracking_species_scores.vl.json; title="Species tracking DetA: $split";;
  assa) target="$folder/${split}_tracking_per_species.csv"; field=AssA; templ=config/plots/tracking_species_scores.vl.json; title="Species tracking AssA: $split";;
  count-mae) target="$folder/${split}_count_per_species.csv"; field=MAE_per_video; templ=config/plots/count_species_mae.vl.json; title="Species count MAE/video: $split";;
  count-compare) target="$folder/${split}_count_per_species.csv"; field=gt_count; templ=config/plots/count_species_comparison.vl.json; title="GT vs predicted fish counts by species: $split";;
  *) echo "Unknown plot kind: $kind" >&2; exit 2;;
esac
if (( $# == 0 )); then
  dvc plots show -t "$templ" -x "$field" -y class_name --title "$title" "$target"
else
  dvc plots diff -t "$templ" -x "$field" -y class_name --title "$title" --targets "$target" -- "$@"
fi
