#!/bin/bash

# ============================================================================
#
# update-help.sh
#
# Update help files by creating JSON files from the original YAML files
#
# Copyright (C) 2021 Rainer Schwarzbach
#
# This file is part of pyxelate.
#
# pyxelate is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyxelate is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyxelate (see LICENSE).
# If not, see <http://www.gnu.org/licenses/>.
#
# ============================================================================

SCRIPT_PATH=$(dirname $0)

for topic in pixelate_image pixelate_video ; do
    file_stub="${SCRIPT_PATH}/docs/${topic}_help"
    ${SCRIPT_PATH}/configfile.py translate ${file_stub}.yaml ${file_stub}.json --overwrite
done
