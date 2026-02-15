#!/bin/bash
cd "$(dirname "$0")"
source /opt/anaconda3/envs/metal/bin/python
conda init
conda activate metal
python server.py "$@"
