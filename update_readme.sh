#!/bin/bash

CURRENT_DATE=$(date +"%a %d %b %Y %H:%M:%S %z")

sed -i "/^\[archlinux@wesley github\]# date$/{
    n
    s/^.*/$CURRENT_DATE/
}" README.md
