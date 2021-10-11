#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

test_pixelate.py

test the pixelate module

Copyright (C) 2021 Rainer Schwarzbach

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
If not, see <http://www.gnu.org/licenses/>.

"""

import argparse
import logging
import pathlib
import sys

# local module

from pyxelate import pixelations


#
# Functions
#


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(description="Pixelate test")
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
    argument_parser.add_argument(
        "image_file", nargs="?", type=pathlib.Path, help="An image file"
    )
    argument_parser.add_argument("dummy", nargs=argparse.REMAINDER)
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    logging.basicConfig(
        format="%(levelname)-8s\u2551 %(funcName)s → %(message)s",
        level=arguments.loglevel,
    )
    selected_file = arguments.image_file
    #
    image_data = pixelations.ImagePixelation(selected_file)
    image_data.set_shape((0, 0), "ellipse", (200, 200))
    base_dir = selected_file.parent
    base_name = selected_file.name
    logging.info("Original size: %r", image_data.original.size)
    logging.info("Original mode: %r", image_data.original.mode)
    logging.info("Pixelated area size: %r", image_data.pixelated_area.size)
    logging.info("Pixelated area mode: %r", image_data.pixelated_area.mode)
    image_data.pixelated_area.save(base_dir / ("px-area_%s" % base_name))
    image_data.result.save(base_dir / ("px-result_%s" % base_name))


if __name__ == "__main__":
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
