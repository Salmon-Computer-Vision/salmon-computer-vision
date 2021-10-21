#!/usr/bin/env bash

jq '(.[].attributes[].mutable | if . == "False" then . else empty end) |= false' $1 | \
    jq '(.[].attributes[].mutable | if . == "True" then . else empty end) |= true' | \
    jq '(.[].attributes[].values | if type=="string" then . else empty end) |= split("\n")'
