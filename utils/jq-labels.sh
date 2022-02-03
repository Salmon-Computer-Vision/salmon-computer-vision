#!/usr/bin/env bash

jq '.[].attributes |= if type=="object" then .attribute else . end' $1 | \
  jq '(.[].attributes[].mutable | if . == "False" then . else empty end) |= false' | \
  jq '(.[].attributes[].mutable | if . == "True" then . else empty end) |= true' | \
  jq '(.[].attributes[].values | if type=="string" then . else empty end) |= split("\n")'
