#!/bin/bash
. /home/twak/miniconda3/bin/activate drdt
cd /home/twak/code/drdt
flask --app api/app run --host=129.169.73.137
