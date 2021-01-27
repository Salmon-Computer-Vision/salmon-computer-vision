#!/usr/bin/env bash

jq '[.[] | .attributes[].mutable |= false]' $1 | \
    jq '[.[] | .attributes[].values |= split("\n")]'
