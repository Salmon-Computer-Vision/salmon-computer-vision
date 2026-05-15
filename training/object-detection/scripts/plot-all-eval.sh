#!/usr/bin/env bash
dvc plots diff --title "$1" -t config/site_resolve_independent_bars_with_values.vl.json $(dvc exp list --name-only | grep '^eval-site-')
