#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

test_pixelate.py

test the pixelate module
"""

import argparse
import logging
import pathlib
import sys

import pixelations


#
# Functions
#


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description='Pixelate test')
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
        '-f', '--file',
        type=pathlib.Path,
        help='An image file')
    argument_parser.add_argument(
        'dummy',
        nargs=argparse.REMAINDER)
    return argument_parser.parse_args()


def main(arguments=None):
    """Main script function"""
    selected_file = None
    try:
        loglevel = arguments.loglevel
        selected_file = arguments.file
    except AttributeError:
        loglevel = logging.WARNING
    #
    if selected_file and not selected_file.is_file():
        selected_file = None
    #
    logging.basicConfig(
        format='%(levelname)-8s\u2551 %(funcName)s → %(message)s',
        level=loglevel)
    #
    image_data = pixelations.ImageData(selected_file)
    image_data.set_shape((0, 0), 'ellipse', (200, 200))
    base_dir = selected_file.parent
    base_name = selected_file.name
    logging.info('Original size: %r', image_data.original.size)
    logging.info('Original mode: %r', image_data.original.mode)
    logging.info('Pixelated size: %r', image_data.pixelated_full.size)
    logging.info('Pixelated mode: %r', image_data.pixelated_full.mode)
    image_data.pixelated_full.save(base_dir / ('fullpx_%s' % base_name))
    image_data.result.save(base_dir / ('result_%s' % base_name))


if __name__ == '__main__':
    # =========================================================================
    # Workaround for unexpected behavior when called
    # as a Nautilus script in combination with argparse
    # =========================================================================
    try:
        sys.exit(main(__get_arguments()))
    except Exception:
        sys.exit(main())
    #


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
