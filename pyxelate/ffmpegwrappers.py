# -*- coding: utf-8 -*-

"""

ffmpegwrappers.py

Module wrapping ffmpeg and ffprobe

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


import logging
import os
import subprocess
import sys
import threading
import time

from queue import Queue


#
# Constants
#


SUBPROCESS_DEFAULTS = dict(
    close_fds=True, stderr=subprocess.PIPE, stdout=subprocess.PIPE
)

if sys.platform == "win32":
    del SUBPROCESS_DEFAULTS["close_fds"]
#

FFMPEG = "ffmpeg"
FFPROBE = "ffprobe"

DEFAULT_LOGLEVEL = "quiet"
DEFAULT_STREAM = "v"
DEFAULT_ENTRIES = "stream=index,avg_frame_rate,r_frame_rate,duration,nb_frames"
DEFAULT_OUTPUT_FORMAT = "default=noprint_wrappers=1"
ENTRIES_ALL = "stream"


#
# Classes
#


class AsynchronousLineReader(threading.Thread):
    """Helper class to implement asynchronous
    line-per-line reading of a stream in a separate thread.
    Pushes read lines on a queue to be consumed in another thread.

    Adapted from <https://github.com/soxofaan/asynchronousfilereader>
    """

    def __init__(self, stream, autostart=True):
        self._stream = stream
        self.queue = Queue()
        threading.Thread.__init__(self)
        if autostart:
            self.start()
        #

    def run(self):
        """The body of the thread:
        read lines and put them on the queue.
        """
        while True:
            time.sleep(0)
            line = self._stream.readline()
            if not line:
                break
            self.queue.put(line)
        #

    def eof(self):
        """Check whether there is no more content to expect."""
        return not self.is_alive() and self.queue.empty()

    def readlines(self):
        """Get currently available lines."""
        while not self.queue.empty():
            yield self.queue.get()
        #


class ProcessWrapper:

    """Process wrapper base class"""

    default_executable = "Executable not set"

    def __init__(self, *arguments, executable=None):
        """Store the arguments and the executable"""
        self.__executable = executable or self.default_executable
        self.__extra = []
        self.__arguments = list(arguments)
        self.result = None

    @property
    def command(self):
        """Executable followed by extra and normal arguments"""
        cmd = [self.__executable] + self.__extra + self.__arguments
        logging.debug("Command: %r", cmd)
        return cmd

    def add_extra_arguments(self, *extra_arguments):
        """Insert extra arguments before all others,
        but try to avoid duplicates
        """
        if extra_arguments[0] not in self.__arguments:
            self.__extra.extend(extra_arguments)
        #

    def __prevent_repeated_execution(self):
        """Prevent repeated execution"""
        if self.result:
            raise ValueError("The process has already been executed!")
        #

    def run(self, check=True, **kwargs):
        """Run the process using subprocess.run()
        and return the result, but store it as well
        """
        self.__prevent_repeated_execution()
        kwargs.update(SUBPROCESS_DEFAULTS)
        self.result = subprocess.run(self.command, check=check, **kwargs)
        return self.result

    def stream(self, check=True, **kwargs):
        """Generator method running the process using subprocess.Popen(),
        logging all stderr lines, yielding all stdout linesm
        and storing the result
        """
        self.__prevent_repeated_execution()
        kwargs.update(SUBPROCESS_DEFAULTS)
        collected_stdout = []
        collected_stderr = []
        process = subprocess.Popen(self.command, **kwargs)
        stderr_reader = AsynchronousLineReader(process.stderr)
        stdout_reader = AsynchronousLineReader(process.stdout)
        while not stdout_reader.eof() or not stderr_reader.eof():
            # Collect stderr and stdout,
            # then sleep a short time before polling again
            for line in stderr_reader.readlines():
                collected_stderr.append(line)
                logging.error(line.decode().rstrip())
            #
            for line in stdout_reader.readlines():
                collected_stdout.append(line)
                yield line.decode().rstrip()
                #
            time.sleep(0.1)
        # Cleanup:
        # Wait for the threads to end and close the file descriptors
        stderr_reader.join()
        stdout_reader.join()
        process.stderr.close()
        process.stdout.close()
        self.result = subprocess.CompletedProcess(
            args=process.args,
            returncode=process.wait(),
            stdout=b"\n".join(collected_stdout),
            stderr=b"\n".join(collected_stderr),
        )
        if check:
            self.result.check_returncode()
        #


class FFmpegWrapper(ProcessWrapper):

    """Wrapper for ffmpeg"""

    default_executable = FFMPEG

    def stream(self, check=True, **kwargs):
        """Set extra arguments"""
        self.add_extra_arguments("-progress", "-")
        return super().stream(check=check, **kwargs)


#
# Functions
#


def get_stream_info(
    file_path,
    ffprobe_executable=FFPROBE,
    select_streams=DEFAULT_STREAM,
    show_entries=DEFAULT_ENTRIES,
    output_format=DEFAULT_OUTPUT_FORMAT,
    loglevel=DEFAULT_LOGLEVEL,
):
    """Return a dict containing the selected entries"""
    ffprobe_exec = ProcessWrapper(
        "-select_streams",
        select_streams,
        "-show_entries",
        show_entries,
        "-of",
        output_format,
        str(file_path),
        executable=ffprobe_executable,
    )
    ffprobe_exec.add_extra_arguments("-loglevel", loglevel)
    ffprobe_result = ffprobe_exec.run(check=True)
    stream_info = {}
    for line in ffprobe_result.stdout.decode().splitlines():
        key, value = line.split("=", 1)
        stream_info[key] = value
        # logging.debug("Read %r = %r", key, value)
    #
    return stream_info


def count_all_frames(
    file_path, ffmpeg_executable=FFMPEG, loglevel=DEFAULT_LOGLEVEL
):
    """Return the last progress block
    of the video frame-by-frame examination as a dict
    """
    read_data = {}
    ffmpeg_exec = FFmpegWrapper(
        "-i",
        str(file_path),
        "-f",
        "rawvideo",
        "-y",
        os.devnull,
        executable=ffmpeg_executable,
    )
    ffmpeg_exec.add_extra_arguments("-loglevel", loglevel)
    try:
        for line in ffmpeg_exec.stream(check=True):
            if line == "progress=continue":
                read_data.clear()
                continue
            #
            try:
                (key, value) = line.split("=", 1)
            except ValueError:
                continue
            #
            read_data[key] = value
        #
    finally:
        return read_data
    #


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
