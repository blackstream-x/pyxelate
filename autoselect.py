#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

autoselect.py

Automatically select the correct script for pixelating
an image or a video clip, based on the provided file's
mime type.

Directly supports Nautilus integration.

"""


import argparse
import logging
import mimetypes
import os
import pathlib
import subprocess
import sys

from tkinter import messagebox


#
# Constants
#


SCRIPT_NAME = 'Autoselect pixelation script'
HOMEPAGE = 'https://github.com/blackstream-x/pyxelate'
MAIN_WINDOW_TITLE = 'pyxelate: autoselect pixelation script'

SCRIPT_PATH = pathlib.Path(os.path.realpath(sys.argv[0]))
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

NAUTILUS_SCRIPTS = pathlib.Path('.local/share/nautilus/scripts')

RETURNCODE_OK = 0
RETURNCODE_ERROR = 1


#
# Functions
#


def install_nautilus_script(name):
    """Install this script as a nautilus script"""
    target_directory = pathlib.Path.home() / NAUTILUS_SCRIPTS
    if not target_directory.is_dir():
        if target_directory.parent.is_dir():
            target_directory.mkdir()
        else:
            logging.error('Nautilus probably not available.')
            return RETURNCODE_ERROR
        #
    #
    target_link_path = target_directory / name
    logging.debug('Target link path: %s', target_link_path)
    if target_link_path.exists():
        logging.error('Nautilus script %r already exists!', name)
        return RETURNCODE_ERROR
    #
    for single_path in target_directory.glob('*'):
        if single_path.is_symlink():
            logging.debug('Found symlink: %s', single_path)
            if single_path.readlink() == SCRIPT_PATH:
                logging.warning(
                    'Nautilus script already installed as %r',
                    single_path.name)
                answer = input(
                    f'Rename that to {name!r} (yes/no)? ').lower() or 'no'
                if 'yes'.startswith(answer):
                    logging.info('Renaming %r to %r.', single_path.name, name)
                    os.rename(single_path, target_link_path)
                    return RETURNCODE_OK
                #
                if 'no'.startswith(answer):
                    logging.info('Leaving everything as is.')
                    return RETURNCODE_OK
                #
                logging.warning(
                    'Interpreting %r as %r, leaving everything as is.',
                    answer, 'no')
                return RETURNCODE_ERROR
            #
        #
    #
    os.symlink(SCRIPT_PATH, target_link_path)
    logging.info('Nautilus script has been installed as %r', name)
    return RETURNCODE_OK


def start_matching_script(file_path):
    """Start the script suitable for the given file path"""
    file_type = mimetypes.guess_type(str(file_path))[0]
    matching_script = None
    if file_type:
        if file_type.startswith('image/'):
            matching_script = 'pixelate_image.py'
        elif file_type.startswith('video/'):
            matching_script = 'pixelate_video.py'
        #
    #
    if matching_script:
        matching_script_path = SCRIPT_PATH.parent / matching_script
        if not matching_script_path.is_file():
            messagebox.showerror(
                'Script not available',
                f'The script handling {file_type} files'
                ' is not available yet.',
                icon=messagebox.ERROR)
            return RETURNCODE_ERROR
        #
        command = []
        if sys.platform == 'win32':
            command = ['pythonw']
        #
        command.append(str(matching_script_path))
        command.append(str(file_path))
        return subprocess.run(command, check=True).returncode
    #
    messagebox.showerror(
        'Wrong file type',
        f'{file_path.name!r} is a file of type {file_type!r},'
        ' but an image or a video is required.',
        icon=messagebox.ERROR)
    return RETURNCODE_ERROR


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
        metavar='NAME',
        const='Pixelate',
        help='Install this script as Nautilus script %(metavar)s'
        ' (default: %(const)s)')
    argument_parser.add_argument(
        'files',
        type=pathlib.Path,
        nargs=argparse.REMAINDER)
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    logging.basicConfig(
        format='%(levelname)-8s\u2551 %(message)s',
        level=arguments.loglevel)
    if arguments.install_nautilus_script:
        return install_nautilus_script(arguments.install_nautilus_script)
    #
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
    logging.error('No (existing) file selected.')
    return RETURNCODE_ERROR


if __name__ == '__main__':
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
