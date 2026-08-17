#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
python main.py --listen 127.0.0.1 --port 8000 --force-fp16
