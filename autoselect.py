#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

autoselect.py

Automatically select the correct script for pixelating
an image or a video clip, based on the provided file's
mime type.
Supports Nautilus integration

"""


import argparse
import logging
import mimetypes
import os
import pathlib
# import re
import subprocess
import sys
# import tkinter
# import webbrowser

# from tkinter import filedialog
# from tkinter import messagebox
# from tkinter import ttk

# local modules

# import pixelate

#
# Constants
#


SCRIPT_NAME = 'Autoselect pixelation script'
HOMEPAGE = 'https://github.com/blackstream-x/pyxelate'
MAIN_WINDOW_TITLE = 'pyxelate: autoselect pixelation script'

SCRIPT_PATH = pathlib.Path(sys.argv[0])
# Follow symlinks
if SCRIPT_PATH.is_symlink():
    SCRIPT_PATH = SCRIPT_PATH.readlink()
#

LICENSE_PATH = SCRIPT_PATH.parent / 'LICENSE'
try:
    LICENSE_TEXT = LICENSE_PATH.read_text()
except OSError as error:
    LICENSE_TEXT = '(License file is missing: %s)' % error
#

VERSION_PATH = SCRIPT_PATH.parent / 'version.txt'
try:
    VERSION = VERSION_PATH.read_text().strip()
except OSError as error:
    VERSION = '(Version file is missing: %s)' % error
#

#
# Helper Functions
#


...


#
# Classes
#


#
# Functions
#


def install_nautilus_script(name):
    """Install this script as a nautilus script"""
    # TODO: ln -s $(readlink -f autoselect.py)
    # ~/.local/share/nautilus/scripts/{name}
    # or os.symlink
    raise NotImplementedError


def start_matching_script(file_path):
    """Start the script suitable for the given file path"""
    file_type = mimetypes.guess_type(file_path)[0]
    matching_script = None
    if file_type:
        if file_type.startswith('image/'):
            matching_script = 'pixelate_image.py'
        elif file_type.startswith('video/'):
            matching_script = 'pixelate_video.py'
        #
    #
    if matching_script:
        return subprocess.run(
            (str(SCRIPT_PATH.parent / matching_script), str(file_path)),
            check=True).returncode
    #
    raise ValueError('No script for file type %r!' % file_type)


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description='Autoselect pixelation script')
    argument_parser.set_defaults(loglevel=logging.INFO)
    argument_parser.add_argument(
        '-v', '--verbose',
        action='store_const',
        const=logging.DEBUG,
        dest='loglevel',
        help='Output all messages including debug level')
    argument_parser.add_argument(
        '-q', '--quiet',
        action='store_const',
        const=logging.WARNING,
        dest='loglevel',
        help='Limit message output to warnings and errors')
    argument_parser.add_argument(
        '--install-nautilus-script',
        nargs='?',
        const='Pixelate',
        help='Install this as a Nautilus script')
    argument_parser.add_argument(
        'files',
        type=pathlib.Path,
        nargs=argparse.REMAINDER)
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    logging.basicConfig(
        format='%(levelname)-8s\u2551 %(funcName)s → %(message)s',
        level=arguments.loglevel)
    try:
        selected_file = arguments.files[0]
    except IndexError:
        selected_file = None
    else:
        if not selected_file.is_file():
            selected_file = None
        #
    #
    try:
        selected_names = os.environ['NAUTILUS_SCRIPT_SELECTED_FILE_PATHS']
    except KeyError:
        pass
    else:
        for name in selected_names.splitlines():
            if name:
                current_path = pathlib.Path(name)
                if current_path.is_file():
                    selected_file = current_path
                    break
                #
            #
        #
    #
    if selected_file:
        return start_matching_script(selected_file)
    #
    return 1


if __name__ == '__main__':
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
