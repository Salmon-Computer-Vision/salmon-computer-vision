#!/usr/bin/env bash
dvc plots diff -t config/site_resolve_independent_bars.vl.json $(dvc exp list --name-only | grep '^eval-site-')
