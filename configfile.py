#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

configfile.py

handle YAML and JSON configuration files

"""


import argparse
import datetime
import difflib
import json
import os
import pathlib
import sys

try:
    import yaml
    YAML_SUPPORTED = True
except ImportError:
    YAML_SUPPORTED = False
#


#
# Constants
#

SCRIPT_NAME = 'Config file handler'
HOMEPAGE = 'https://github.com/blackstream-x/pyxelate'

SCRIPT_PATH = pathlib.Path(os.path.realpath(sys.argv[0]))
# Follow symlinks
if SCRIPT_PATH.is_symlink():
    SCRIPT_PATH = SCRIPT_PATH.readlink()
#

LICENSE_PATH = SCRIPT_PATH.parent / 'LICENSE'
COPYRIGHT_NOTICE = """Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the MIT License.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the LICENSE file for more details."""

VERSION_PATH = SCRIPT_PATH.parent / 'version.txt'
try:
    VERSION = VERSION_PATH.read_text().strip()
except OSError as error:
    VERSION = '(Version file is missing: %s)' % error
#

MODE_READ = 'rt'
MODE_WRITE = 'wt'
ENCODING = 'utf-8'

RC_OK = RC_EQUAL = 0
RC_DIFFERENT = 1
RC_ERROR = 2


#
# Exceptions
#


class FiletypeNotSupported(Exception):

    """Raised if an unsupported fie type was encountered"""

    ...


class InvalidFormatError(Exception):

    """Raised if file content is not loadable using the YAML or JSON parser"""

    ...


#
# Functions
#


def load_json(file_name):
    """Load a JSON file"""
    try:
        with open(file_name,
                  mode=MODE_READ,
                  encoding=ENCODING) as input_file:
            return json.load(input_file)
        #
    except json.decoder.JSONDecodeError as json_decode_error:
        raise InvalidFormatError(
            *json_decode_error.args) from json_decode_error
    #


def dump_to_json(data, file_name):
    """Dump data to a JSON file"""
    with open(file_name,
              mode=MODE_WRITE,
              encoding=ENCODING) as output_file:
        json.dump(data, output_file, indent=2)
    #


JSON_FILE = 'JSON file'
YAML_FILE = 'YAML file'

SUPPORTED_FILE_TYPES = {JSON_FILE: ('.json',)}
LOADERS = {JSON_FILE: load_json}
DUMPERS = {JSON_FILE: dump_to_json}

if YAML_SUPPORTED:

    def load_yaml(file_name):
        """Load a YAML file"""
        try:
            with open(file_name,
                      mode=MODE_READ,
                      encoding=ENCODING) as input_file:
                return yaml.safe_load(input_file)
            #
        except yaml.parser.ParserError as yaml_parser_error:
            raise InvalidFormatError(
                'YAML parsing failed:\n{0}'.format(
                    yaml_parser_error.problem)) from yaml_parser_error
        #

    def dump_to_yaml(data, file_name):
        """Dump data to a YAML file"""
        with open(file_name,
                  mode=MODE_WRITE,
                  encoding=ENCODING) as output_file:
            yaml.dump(data, output_file, default_flow_style=False)
        #

    SUPPORTED_FILE_TYPES[YAML_FILE] = ('.yaml', '.yml')
    LOADERS[YAML_FILE] = load_yaml
    DUMPERS[YAML_FILE] = dump_to_yaml
#


#
# Generalized functions
#


def read_file(file_name):
    """Read a YAML or JSON file,
    dispatch to the matching load function
    """
    file_extension = os.path.splitext(file_name)[1]
    for file_type, load_function in LOADERS.items():
        if file_extension in SUPPORTED_FILE_TYPES[file_type]:
            return load_function(file_name)
        #
    #
    raise FiletypeNotSupported(
        'File extension {0!r} not supported'.format(file_extension))


def write_to_file(data, file_name):
    """Dump data to a YAML or JSON file,
    dispatch to the matching dump function
    """
    file_extension = os.path.splitext(file_name)[1]
    for file_type, dump_function in DUMPERS.items():
        if file_extension in SUPPORTED_FILE_TYPES[file_type]:
            dump_function(data, file_name)
            break
        #
    else:
        raise FiletypeNotSupported(
            'File extension {0!r} not supported'.format(file_extension))
    #


def comparable_form(data):
    """Return a serialized form of data to enable comparing data structures.
    Prefer YAML -if supported- over JSON
    """
    if YAML_SUPPORTED:
        return yaml.dump(data, default_flow_style=False, sort_keys=True)
    #
    return json.dumps(data, indent=2, sort_keys=True)


#
# Command line interface
#


def compare_data(arguments):
    """Compare data in the files by dumping both to a JSON string
    and comparing the strings.
    If the --diff switch was specified, write a unified diff of the
    JSON representations.
    """
    file_data = []
    labels = []
    times = []
    for current_file_name in arguments.file_name:
        file_data.append(
            comparable_form(read_file(current_file_name)))
        labels.append(
            'Data from {0}'.format(current_file_name))
        times.append(
            datetime.datetime.fromtimestamp(
                os.stat(current_file_name).st_mtime))
    #
    if file_data[0] == file_data[1]:
        comparison_result = RC_EQUAL
    else:
        comparison_result = RC_DIFFERENT
    #
    if arguments.diff:
        sys.stdout.writelines(
            difflib.unified_diff(
                file_data[0].splitlines(keepends=True),
                file_data[1].splitlines(keepends=True),
                fromfile=labels[0],
                tofile=labels[1],
                fromfiledate=times[0].isoformat(),
                tofiledate=times[1].isoformat()))
    elif arguments.verbose:
        if comparison_result == RC_EQUAL:
            print('Equal data in both files.')
        else:
            print('Different data in the files'
                  ' - use --diff to show details.')
        #
    #
    return comparison_result


def translate_files(arguments):
    """Translate data from the input file to the output file format.
    Overwrite existing files only if the --overwrite option was specified.
    """
    if os.path.exists(arguments.output_file_name):
        if not arguments.overwrite:
            print('The output file {0.output_file_name!r} exists already.'
                  ' Please use the --overwrite option to overwrite'
                  ' existing files.'.format(arguments))
            return RC_ERROR
        #
        if arguments.verbose:
            print('Overwriting the existing file {0.output_file_name!r}'
                  ' as requested'.format(arguments))
        #
    #
    write_to_file(read_file(arguments.input_file_name),
                  arguments.output_file_name)
    return RC_OK


SUBCOMMAND_COMPARE = 'compare'
SUBCOMMAND_TRANSLATE = 'translate'

ACTIONS = {
    SUBCOMMAND_COMPARE: compare_data,
    SUBCOMMAND_TRANSLATE: translate_files,
}


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description='Handle YAML and JSON config files')
    argument_parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Verbose output')
    subparsers = argument_parser.add_subparsers(
        dest='action',
        title='Available subcommands (use {0} <subcommand> --help'
        ' for subcommand details)'.format(sys.argv[0]),
        required=True)
    # Compare files
    parser_compare = subparsers.add_parser(
        SUBCOMMAND_COMPARE,
        help='Compare the data stored in two files.')
    parser_compare.add_argument(
        '--diff',
        action='store_true',
        help='Produce a unified diff output over a representation of data'
        'in each file')
    parser_compare.add_argument(
        'file_name',
        nargs=2,
        help='The files to be compared')
    # Translate files
    parser_translate = subparsers.add_parser(
        SUBCOMMAND_TRANSLATE,
        help='Translate data stored in the input file'
        ' to the output file format.')
    parser_translate.add_argument(
        '--overwrite',
        action='store_true',
        help='Overwrite the output file if it exists')
    parser_translate.add_argument(
        'input_file_name',
        help='The input file')
    parser_translate.add_argument(
        'output_file_name',
        help='The output file')
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    return ACTIONS[arguments.action](arguments)


if __name__ == '__main__':
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
