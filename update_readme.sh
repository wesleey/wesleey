#!/bin/bash

FILE="README.md"

CURRENT_DATE=$(date +"%a %d %b %Y %H:%M:%S %z")

sed -i "/^\[root@archlinux wesley\]# date$/{
    n
    s/^.*/$CURRENT_DATE/
}" "$FILE"
