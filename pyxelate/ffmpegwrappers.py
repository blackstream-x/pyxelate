# -*- coding: utf-8 -*-

"""

ffmpegwrappers.py

Module wrapping ffmpeg and ffprobe

Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the MIT License.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the LICENSE file for more details.

"""


# import io
import logging
import subprocess
import math
import re
# import time

from fractions import Fraction


#
# Constants
#


FFMPEG = 'ffmpeg'
FFPROBE = 'ffprobe'

DEFAULT_VERBOSITY = 'error'
DEFAULT_STREAM = 'v'
DEFAULT_ENTRIES = \
    'stream=index,avg_frame_rate,r_frame_rate,duration,nb_frames'
DEFAULT_OUTPUT_FORMAT = 'default=noprint_wrappers=1'
ENTRIES_ALL = 'stream'


#
# Helper functions
#


def get_stream_info(file_path,
                    verbosity=DEFAULT_VERBOSITY,
                    select_streams=DEFAULT_STREAM,
                    show_entries=DEFAULT_ENTRIES,
                    output_format=DEFAULT_OUTPUT_FORMAT):
    """Return a dict containing the seected entries"""
    ffprobe_result = subprocess.run(
        (
            FFPROBE, '-v', verbosity, '-select_streams', select_streams,
            '-show_entries' ,show_entries, '-of', output_format,
            str(file_path)),
        check=True, stdout=subprocess.PIPE)
    stream_info = {}
    for line in ffprobe_result.stdout.decode().splitlines():
        key, value = line.split('=', 1)
        stream_info[key] = value
        logging.debug('Read %r = %r', key, value)
    #
    return stream_info


#
# Classes
#




# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
