#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

pixelate.py

Automatically select the correct script for pixelating
an image or a video clip, based on the provided file's
mime type.

Directly supports integration into the Nautilus and Nemo filemanagers.

"""


import argparse
import logging
import mimetypes
import os
import pathlib
import string
import subprocess
import sys

from tkinter import messagebox


#
# Constants
#


SCRIPT_NAME = "Automatically select pixelation script"
HOMEPAGE = "https://github.com/blackstream-x/pyxelate"
MAIN_WINDOW_TITLE = "pyxelate: automatically select pixelation script"

SCRIPT_PATH = pathlib.Path(os.path.realpath(sys.argv[0]))
# Follow symlinks
if SCRIPT_PATH.is_symlink():
    SCRIPT_PATH = SCRIPT_PATH.readlink()
#

LICENSE_PATH = SCRIPT_PATH.parent / "LICENSE"
COPYRIGHT_NOTICE = """Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with pyxelate (see LICENSE).
If not, see <http://www.gnu.org/licenses/>."""

VERSION_PATH = SCRIPT_PATH.parent / "version.txt"
try:
    VERSION = VERSION_PATH.read_text().strip()
except OSError as os_error:
    VERSION = f"(Version file is missing: {os_error})"
#

NAUTILUS = "Nautilus"
NEMO = "Nemo"

SCRIPT_DIRECTORIES = {
    NAUTILUS: pathlib.Path(".local/share/nautilus/scripts"),
    NEMO: pathlib.Path(".local/share/nemo/scripts"),
}

SUPPORTED_FILE_MANAGERS = (NAUTILUS, NEMO)

RETURNCODE_OK = 0
RETURNCODE_ERROR = 1

DEFAULT_ACTION_NAME = "Pyxelate"
DEFAULT_ACTION_COMMENT = "pixelate images or video sequences"

NEMO_ACTION_FILE = "pyxelate.nemo_action"
NEMO_ACTION_TEMPLATE = pathlib.Path(
    "integration/pyxelate.nemo_action_template"
)
NEMO_ACTIONS_DIRECTORY = pathlib.Path(".local/share/nemo/actions")

#
# Functions
#


def get_selected_path():
    """Return the path of the first selected existing file
    in any of the supported file managers.
    Raise a ValueError if no such path was found.
    """
    for file_manager_name in SUPPORTED_FILE_MANAGERS:
        try:
            selected_names = os.environ[
                f"{file_manager_name.upper()}_SCRIPT_SELECTED_FILE_PATHS"
            ]
        except KeyError:
            continue
        else:
            for name in selected_names.splitlines():
                if name:
                    current_path = pathlib.Path(name)
                    if current_path.is_file():
                        return current_path
                    #
                #
            #
        #
        # TODO: The environment variable exists, but
        # none of the paths in it is a valid file.
        # This situation should lead to the opening
        # of a file selection window and a subsequent
        # break statement
    #
    raise ValueError("No existing file selected.")


def install_file_manager_script(file_manager_name, display_name):
    """Install this script as a file manager script"""
    target_directory = (
        pathlib.Path.home() / SCRIPT_DIRECTORIES[file_manager_name]
    )
    if not target_directory.is_dir():
        if target_directory.parent.is_dir():
            target_directory.mkdir()
        else:
            logging.error("%s is probably not available.", file_manager_name)
            return RETURNCODE_ERROR
        #
    #
    target_link_path = target_directory / display_name
    logging.debug("Target link path: %s", target_link_path)
    if target_link_path.exists():
        logging.error(
            "%s script %r already exists!", file_manager_name, display_name
        )
        return RETURNCODE_ERROR
    #
    for single_path in target_directory.glob("*"):
        if single_path.is_symlink():
            logging.debug("Found symlink: %s", single_path)
            if single_path.readlink() == SCRIPT_PATH:
                logging.warning(
                    "%s script already installed as %r",
                    file_manager_name,
                    single_path.name,
                )
                answer = (
                    input(
                        f"Rename that to {display_name!r} (yes/no)? "
                    ).lower()
                    or "no"
                )
                if "yes".startswith(answer):
                    logging.info(
                        "Renaming %r to %r.", single_path.name, display_name
                    )
                    os.rename(single_path, target_link_path)
                    return RETURNCODE_OK
                #
                if "no".startswith(answer):
                    logging.info("Leaving everything as is.")
                    return RETURNCODE_OK
                #
                logging.warning(
                    "Interpreting %r as %r, leaving everything as is.",
                    answer,
                    "no",
                )
                return RETURNCODE_ERROR
            #
        #
    #
    os.symlink(SCRIPT_PATH, target_link_path)
    logging.info(
        "%s script has been installed as %r.", file_manager_name, display_name
    )
    return RETURNCODE_OK


def install_nemo_action(arguments):
    """Install this script as a nemo action"""
    target_directory = pathlib.Path.home() / NEMO_ACTIONS_DIRECTORY
    if not target_directory.is_dir():
        if target_directory.parent.is_dir():
            target_directory.mkdir()
        else:
            logging.error("Nemo is probably not installed.")
            return RETURNCODE_ERROR
        #
    #
    with open(
        SCRIPT_PATH.parent / NEMO_ACTION_TEMPLATE, mode="rt", encoding="utf-8"
    ) as template_file:
        template = string.Template(template_file.read())
    #
    comment = DEFAULT_ACTION_COMMENT
    try:
        name = arguments.install_nemo_action.pop(0)
    except IndexError:
        name = DEFAULT_ACTION_NAME
    else:
        try:
            comment = arguments.install_nemo_action.pop(0)
        except IndexError:
            pass
        #
    #
    values = dict(
        name=name,
        comment=comment,
        exec=str(SCRIPT_PATH),
    )
    with open(
        target_directory / NEMO_ACTION_FILE, mode="wt", encoding="utf-8"
    ) as target_file:
        target_file.write(template.safe_substitute(values))
    #
    logging.info("Nemo action %r has been installed.", name)
    return RETURNCODE_OK


def start_matching_script(file_path):
    """Start the script suitable for the given file path"""
    # TODO: implement a loop,
    # showing a file selection dialog if the file type is neither
    # image or video.
    # The RETURNCODE_ERROR should only be returned
    # if the file selection dialog was exited without selecting a file.
    file_type = mimetypes.guess_type(str(file_path))[0]
    matching_script = None
    if file_type:
        if file_type.startswith("image/"):
            matching_script = "pixelate_image.py"
        elif file_type.startswith("video/"):
            matching_script = "pixelate_video.py"
        #
    #
    if matching_script:
        matching_script_path = SCRIPT_PATH.parent / matching_script
        if not matching_script_path.is_file():
            messagebox.showerror(
                "Script not available",
                f"The script handling {file_type} files"
                " is not available yet.",
                icon=messagebox.ERROR,
            )
            return RETURNCODE_ERROR
        #
        command = []
        if sys.platform == "win32":
            command = ["pythonw"]
        #
        command.append(str(matching_script_path))
        command.append(str(file_path))
        return subprocess.run(command, check=True).returncode
    #
    messagebox.showerror(
        "Wrong file type",
        f"{file_path.name!r} is a file of type {file_type!r},"
        " but an image or a video is required.",
        icon=messagebox.ERROR,
    )
    return RETURNCODE_ERROR


def __get_argument_parser():
    """Define command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description="Autoselect pixelation script"
    )
    argument_parser.set_defaults(loglevel=logging.INFO)
    argument_parser.add_argument(
        "-v",
        "--verbose",
        action="store_const",
        const=logging.DEBUG,
        dest="loglevel",
        help="Output all messages including debug level",
    )
    argument_parser.add_argument(
        "-q",
        "--quiet",
        action="store_const",
        const=logging.WARNING,
        dest="loglevel",
        help="Limit message output to warnings and errors",
    )
    mutex_group = argument_parser.add_mutually_exclusive_group()
    mutex_group.add_argument(
        "--install-nautilus-script",
        nargs="?",
        metavar="NAME",
        const=DEFAULT_ACTION_NAME,
        help="Install this script as Nautilus script %(metavar)s"
        " (default: %(const)s)",
    )
    mutex_group.add_argument(
        "--install-nemo-script",
        nargs="?",
        metavar="NAME",
        const=DEFAULT_ACTION_NAME,
        help="Install this script as Nemo script %(metavar)s"
        " (default: %(const)s)",
    )
    mutex_group.add_argument(
        "--install-nemo-action",
        nargs="*",
        metavar="ARG",
        help="Install this script as a Nemo action with"
        " the first %(metavar)s as its name"
        f" (default: {DEFAULT_ACTION_NAME})."
        " If a second %(metavar)s is provided,"
        " it is used as comment for the action, else"
        f" {DEFAULT_ACTION_COMMENT!r} will be used.",
    )
    mutex_group.add_argument(
        "file",
        type=pathlib.Path,
        nargs="?",
        help="The image or video file to pixelate",
    )
    return argument_parser


def main():
    """Main script function"""
    argument_parser = __get_argument_parser()
    arguments = argument_parser.parse_args()
    logging.basicConfig(
        format="%(levelname)-8s\u2551 %(message)s", level=arguments.loglevel
    )
    if arguments.install_nautilus_script:
        return install_file_manager_script(
            NAUTILUS, arguments.install_nautilus_script
        )
    #
    if arguments.install_nemo_script:
        return install_file_manager_script(NEMO, arguments.install_nemo_script)
    #
    if arguments.install_nemo_action is not None:
        return install_nemo_action(arguments)
    #
    selected_file = arguments.file
    if selected_file and not selected_file.is_file():
        selected_file = None
    #
    try:
        selected_file = get_selected_path()
    except ValueError:
        pass
    #
    if selected_file:
        return start_matching_script(selected_file)
    #
    argument_parser.print_help()
    return RETURNCODE_ERROR


if __name__ == "__main__":
    sys.exit(main())


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
