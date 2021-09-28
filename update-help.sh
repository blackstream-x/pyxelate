#!/bin/bash

# ============================================================================
#
# update-help.sh
#
# Update help files by creating JSON files from the original YAML files
#
# This file is part of pyxelate.
#
# pyxelate is free software: you can redistribute it and/or modify
# it under the terms of the MIT License.
#
# pyxelate is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
# See the LICENSE file for more details."""
#
# ============================================================================

SCRIPT_PATH=$(dirname $0)

for topic in pixelate_image pixelate_video ; do
    file_stub="${SCRIPT_PATH}/docs/${topic}_help"
    ${SCRIPT_PATH}/configfile.py translate ${file_stub}.yaml ${file_stub}.json --overwrite
done
