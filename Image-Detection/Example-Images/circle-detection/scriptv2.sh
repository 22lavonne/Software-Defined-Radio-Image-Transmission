#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo "Starting circle detection / encryption 1/3"
python3 -u circledectection.py

echo "Moving to Transmission 2/3"
sleep 2
python3 -u function.py
echo "part 1/3 done"
sleep 3		
python3 -u function.py
echo "part 2/3 done"
sleep 3		
python3 -u function.py
echo "part 3/3 done"

echo "All Transmission Complete 3/3"
