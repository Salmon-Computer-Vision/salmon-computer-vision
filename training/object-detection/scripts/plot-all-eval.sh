#!/usr/bin/env bash
dvc plots diff $(dvc exp list --name-only | grep '^eval-site-')
