#!/bin/bash
# Double-click to download the Polyend community plates and the pedal image.
# Run it again any time to add plates that were published since.
cd "$(dirname "$0")"
/usr/bin/python3 app/setup.py "$@"
echo
read -n 1 -s -r -p "Press any key to close"
