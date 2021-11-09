#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

pixelate_video.py

Partially pixelate selected frames of a (short) video clip
(Tkinter-based GUI assistant)

"""


import argparse
import logging
import mimetypes
import os
import pathlib
import subprocess
import sys
import tempfile
import tkinter

from fractions import Fraction

from tkinter import filedialog
from tkinter import messagebox

# local modules

from pyxelate import core
from pyxelate import ffmpegwrappers as ffmw
from pyxelate import gui
from pyxelate import pixelations


#
# Constants
#


SCRIPT_NAME = "Partially pixelate a video clip"
HOMEPAGE = "https://github.com/blackstream-x/pyxelate"

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

# Phases
OPEN_FILE = core.UserInterface.phase_open_file
FIRST_FRAME = "first_frame"
LAST_FRAME = "last_frame"
START_AREA = "start_area"
STOP_AREA = "stop_area"
PREVIEW = "preview"

PHASES = (
    OPEN_FILE,
    FIRST_FRAME,
    LAST_FRAME,
    START_AREA,
    STOP_AREA,
    PREVIEW,
)

PANEL_NAMES = {
    FIRST_FRAME: "Cut your video: select the beginning of the desired clip",
    LAST_FRAME: "Cut your video: select the end of the desired clip",
    START_AREA: "Pixelate a segment: select a start frame and area",
    STOP_AREA: "Pixelate a segment: select an end frame and area",
    PREVIEW: "Preview the modified video frame by frame",
}

EMPTY_SELECTION = dict(
    frame=None,
    shape=None,
    center_x=None,
    center_y=None,
    width=None,
    height=None,
)

MAX_NB_FRAMES = 10000

ONE_MILLION = 1000000

# DEFAULT_EXPORT_CRF = 18
# DEFAULT_EXPORT_PRESET = "ultrafast"

EXPORT_PRESETS = (
    "ultrafast",
    "superfast",
    "veryfast",
    "faster",
    "fast",
    "medium",
    "slow",
    "slower",
    "veryslow",
)

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 540

# DEFAULT_TILESIZE = 10


#
# Classes
#


class TemporaryFramesPath(core.InterfacePlugin):

    """Context manager for a temporary directory with files from
    the modified_frames and original_frames directory
    """

    def __init__(self, application):
        """Store the provided information and provide
        a storage for files source
        """
        super().__init__(application)
        self.source_file = {}
        self.temporary_storage = None

    def __enter__(self):
        """Create the temporary directory.
        Move files here (from the primary or, if not found,
        from the secondary directory
        store the original name for each file
        Return the name of the current tempdir as a Path instance
        """
        source_paths = []
        for source_tempdir in (
            self.vars.modified_frames,
            self.vars.original_frames,
        ):
            try:
                source_paths.append(pathlib.Path(source_tempdir.name))
            except AttributeError:
                pass
            #
        #
        self.temporary_storage = tempfile.TemporaryDirectory()
        logging.debug("Created tempdir %r", self.temporary_storage.name)
        temporary_path = pathlib.Path(self.temporary_storage.name)
        new_number = 1
        for old_number in range(
            self.vars.kept_frames.start, self.vars.kept_frames.end + 1
        ):
            old_file_name = pixelations.FRAME_PATTERN % old_number
            new_file_name = pixelations.FRAME_PATTERN % new_number
            for single_source_path in source_paths:
                old_path = single_source_path / old_file_name
                if old_path.is_file():
                    self.source_file[new_file_name] = str(old_path)
                    old_path.rename(temporary_path / new_file_name)
                    break
                #
            else:
                raise ValueError(
                    f"File {old_file_name!r} found neither in modified"
                    " nor in original frames!"
                )
            #
            new_number += 1
        #
        logging.debug("Moved %r files", new_number - 1)
        return temporary_path

    def __exit__(self, exc_type, exc_value, traceback):
        """Move the files back
        Cleanup the temporary directory
        """
        temporary_path = pathlib.Path(self.temporary_storage.name)
        for file_path in temporary_path.glob("*"):
            original_name = self.source_file[file_path.name]
            file_path.rename(original_name)
        #
        logging.debug("Moved files back to the original directories")
        self.temporary_storage.cleanup()
        logging.debug(
            "Deleted temporary directory %s", self.temporary_storage.name
        )


class Actions(core.InterfacePlugin):

    """Pre-panel actions for the video GUI in sequential order"""

    def first_frame(self):
        """Actions before showing "first frame" selection"""
        self.application.adjust_frame_limits()
        self.vars.update(
            image=pixelations.BaseImage(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            ),
            frame_position="Select first video",
        )
        # set the show_preview variable to the user setting
        self.tkvars.show_preview.set(self.vars.user_settings.show_preview)
        self.application.set_default_selection(
            tilesize=self.vars.user_settings.tilesize
        )

    def last_frame(self):
        """Actions before showing "first frame" selection"""
        self.application.adjust_frame_limits()
        self.vars.update(
            image=pixelations.BaseImage(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            ),
            frame_position="Select last video",
        )

    def start_area(self):
        """Actions before showing the start area selection panel:
        Load the frame and set the variables
        """
        self.application.adjust_frame_limits()
        self.vars.update(
            image=pixelations.FramePixelation(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            ),
            frame_position="Pixelation start",
        )
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        #
        try:
            self.application.apply_coordinates(self.vars.later_stations.pop())
        except IndexError:
            self.application.adjust_current_frame(self.vars.kept_frames.start)
        #
        self.tkvars.drag_action.set(self.vars.previous_drag_action)

    def stop_area(self):
        """Actions before showing the stop area selection panel:
        Save the coordinates
        Fix the currently selected frame as start frame.
        Load the frame for area selection
        """
        self.application.adjust_frame_limits(
            minimum=self.tkvars.current_frame.get()
        )
        try:
            self.application.apply_coordinates(self.vars.later_stations.pop())
        except IndexError:
            pass
        #
        self.vars.update(
            image=pixelations.FramePixelation(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            ),
            frame_position="Pixelation stop",
        )
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        #

    def preview(self):
        """Actions before showing the preview panel:
        Fix the selected end coordinates
        Apply the pixelations to all images
        """
        self.application.adjust_frame_limits()
        try:
            self.application.apply_coordinates(self.vars.later_stations.pop())
        except IndexError:
            pass
        #
        self.vars.update(
            previous_drag_action=self.tkvars.drag_action.get(),
            frame_position="Current",
        )
        self.tkvars.drag_action.set(core.NEW_CROP_AREA)


class Callbacks(core.Callbacks):

    """Callback functions for the video UI"""

    def change_frame(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        try:
            self.widgets.canvas.delete(core.TAG_IMAGE)
        except AttributeError as error:
            logging.warning("%s", error)
        except tkinter.TclError as error:
            logging.warning("%s", error)
            return
        #
        # Adjust to current limits
        self.application.adjust_current_frame()
        image_type = pixelations.BaseImage
        frame_path = (
            pathlib.Path(self.vars.original_frames.name) / self.vars.frame_file
        )
        if self.vars.current_panel == PREVIEW:
            try:
                modified_frames_dir = self.vars.modified_frames.name
            except AttributeError:
                pass
            else:
                modified_path = (
                    pathlib.Path(modified_frames_dir) / self.vars.frame_file
                )
                if modified_path.is_file():
                    frame_path = modified_path
                #
            #
        elif self.vars.current_panel in (START_AREA, STOP_AREA):
            image_type = pixelations.FramePixelation
        #
        self.vars.update(
            image=image_type(
                frame_path,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            )
        )
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        #
        self.vars.update(tk_image=self.vars.image.tk_original)
        self.widgets.canvas.create_image(
            0,
            0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags=core.TAG_IMAGE,
        )
        if self.vars.current_panel in (START_AREA, STOP_AREA):
            self.application.draw_indicator()
            self.application.pixelate_selection()
        #

    def change_frame_from_text(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        self.tkvars.current_frame.set(
            int(self.tkvars.current_frame_text.get())
        )

    def frame_decrement(self, *unused_event):
        """Decrement frame number"""
        current_frame = self.tkvars.current_frame.get()
        self.application.adjust_current_frame(current_frame - 1)
        self.change_frame()

    def frame_increment(self, *unused_event):
        """increment frame number"""
        current_frame = self.tkvars.current_frame.get()
        self.application.adjust_current_frame(current_frame + 1)
        self.change_frame()

    def set_export_preferences(self, *unused_arguments):
        """Set the export_crf and export_preset user preferences
        from the tkvars"""
        self.vars.user_settings.update(
            export_crf=self.tkvars.export.crf.get(),
            export_preset=self.tkvars.export.preset.get(),
        )

    def set_include_audio_preference(self):
        """Set the prefer_include_audio user preference
        from the tkvar
        """
        self.vars.user_settings.update(
            prefer_include_audio=bool(self.tkvars.export.include_audio.get())
        )

    def toggle_crop_display(self, *unused_arguments):
        """Toggle crop area preview update"""
        if not self.vars.trace:
            return
        #
        if self.vars.current_panel in (PREVIEW, FIRST_FRAME, LAST_FRAME):
            self.change_frame()
            return
        #
        super().toggle_crop_display(*unused_arguments)

    def update_buttons(self, *unused_arguments):
        """Trigger previous, next and save button states changes"""
        ...


class Panels(core.Panels):

    """Panels and panel components"""

    # Components

    def component_image_on_canvas(self):
        """Show the image on a canvas, with a slider"""
        image_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        prev_button = tkinter.Button(
            image_frame,
            text="\u2190",
            command=self.application.callbacks.frame_decrement,
        )
        label = tkinter.Label(
            image_frame,
            text=f"{self.vars.frame_position} frame fine-tune:",
        )
        next_button = tkinter.Button(
            image_frame,
            text="\u2192",
            command=self.application.callbacks.frame_increment,
        )
        label.grid(row=0, column=1, padx=5, pady=5)
        prev_button.grid(row=0, column=2, padx=5, pady=5)
        next_button.grid(row=0, column=3, padx=5, pady=5)
        logging.debug("Destroying pre-existing slider")
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frames_slider.destroy()
        except AttributeError:
            pass
        #
        logging.debug("Showing slider")
        self.widgets.frames_slider = tkinter.Scale(
            image_frame,
            from_=self.vars.frame_limits.minimum,
            to=self.vars.frame_limits.maximum,
            length=self.vars.canvas_width,
            # label=f"{self.vars.frame_position} frame:",
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame,
        )
        self.widgets.frames_slider.grid(columnspan=5)
        logging.debug("Showing canvas")
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=self.vars.canvas_width,
            height=self.vars.canvas_height,
        )
        self.widgets.canvas.grid(columnspan=5)
        image_frame.columnconfigure(0, weight=100)
        image_frame.columnconfigure(4, weight=100)
        self.vars.update(trace=True)
        if self.vars.current_panel in (START_AREA, STOP_AREA, PREVIEW):
            if self.vars.current_panel in (START_AREA, STOP_AREA):
                self.application.draw_indicator()
                self.application.pixelate_selection()
            #
            # add bindings
            self.widgets.canvas.bind(
                "<ButtonPress-1>", self.application.callbacks.drag_start
            )
            self.widgets.canvas.bind(
                "<ButtonRelease-1>", self.application.callbacks.drag_stop
            )
            self.widgets.canvas.bind(
                "<B1-Motion>", self.application.callbacks.drag_move
            )
            # Set the canvas cursor
            self.application.callbacks.set_canvas_cursor()
        #
        self.application.callbacks.change_frame()
        image_frame.grid(row=1, column=0, rowspan=3, **core.GRID_FULLWIDTH)

    def component_frameselection(self):
        """Select the start or end frame using a slider
        and show that frame on a canvas
        """
        self.component_image_on_canvas()
        self.sidebar_frameselection()

    def component_export_settings(self, sidebar_frame, parent_window=None):
        """Section with the export settings"""
        # Disable "include audio" if the original video
        # has no audio stream
        if self.vars.has_audio:
            include_audio_state = tkinter.NORMAL
        else:
            self.tkvars.export.include_audio.set(0)
            include_audio_state = tkinter.DISABLED
        #
        self.application.heading_with_help_button(
            sidebar_frame, "Export settings", parent_window=parent_window
        )
        label = tkinter.Label(sidebar_frame, text="CRF:")
        crf = tkinter.Spinbox(
            sidebar_frame,
            from_=0,
            to=51,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.export.crf,
        )
        label.grid(sticky=tkinter.W, column=0)
        crf.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(sidebar_frame, text="Preset:")
        preset_opts = tkinter.OptionMenu(
            sidebar_frame, self.tkvars.export.preset, *EXPORT_PRESETS
        )
        label.grid(sticky=tkinter.W, column=0)
        preset_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=4,
        )
        include_audio = tkinter.Checkbutton(
            sidebar_frame,
            anchor=tkinter.W,
            command=self.application.callbacks.set_include_audio_preference,
            text="Include original audio",
            variable=self.tkvars.export.include_audio,
            indicatoron=1,
            state=include_audio_state,
        )
        include_audio.grid(
            sticky=tkinter.W,
            column=0,
            columnspan=5,
        )

    def component_image_info(self, parent_frame):
        """Show information about the current video frame"""
        self.application.heading_with_help_button(
            parent_frame, f"{self.vars.frame_position} frame"
        )
        label = tkinter.Label(parent_frame, text="Number:")
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frame_number.destroy()
        except AttributeError:
            pass
        #
        self.widgets.update(
            frame_number=tkinter.Spinbox(
                parent_frame,
                from_=self.vars.frame_limits.minimum,
                to=self.vars.frame_limits.maximum,
                textvariable=self.tkvars.current_frame_text,
                state="readonly",
                width=4,
            )
        )
        label.grid(sticky=tkinter.W)
        self.widgets.frame_number.grid(
            sticky=tkinter.W,
            columnspan=3,
            column=1,
            row=gui.grid_row_of(label),
        )
        self.component_zoom_factor(parent_frame)
        if self.vars.current_panel in (START_AREA, STOP_AREA, PREVIEW):
            crop_active = tkinter.Checkbutton(
                parent_frame,
                anchor=tkinter.W,
                text="Crop video",
                variable=self.tkvars.crop,
                indicatoron=1,
            )
            crop_active.grid(
                sticky=tkinter.W,
                column=0,
                columnspan=5,
            )
        #

    def sidebar_frameselection(self):
        """Show the frame selection sidebar"""
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_file_info(sidebar_frame)
        self.component_image_info(sidebar_frame)
        self.component_show_preview(sidebar_frame, subject="before saving")
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(row=0, column=1, rowspan=2, **core.GRID_FULLWIDTH)

    def sidebar_preview(self):
        """Show the preview sidebar"""
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_file_info(sidebar_frame)
        self.component_image_info(sidebar_frame)
        self.component_select_drag_action(
            sidebar_frame, supported_actions=[core.NEW_CROP_AREA]
        )
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(row=0, column=1, rowspan=2, **core.GRID_FULLWIDTH)

    def sidebar_export(self):
        """Show the export sidebar"""
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_export_settings(sidebar_frame)
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(
            row=2,
            column=1,
            padx=4,
            pady=2,
            sticky=tkinter.E + tkinter.W + tkinter.S,
        )

    # Panels in order of appearance

    def first_frame(self):
        """Select the first frame using a slider
        and show that frame on a canvas
        """
        self.component_image_on_canvas()
        self.sidebar_frameselection()

    last_frame = first_frame

    def start_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.component_image_on_canvas()
        self.sidebar_settings(preview_subject="pixelation / before saving")

    def stop_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        if self.vars.stations[-1]["shape"] in core.ELLIPTIC_SHAPES:
            allowed_shapes = core.ELLIPTIC_SHAPES
        else:
            allowed_shapes = core.RECTANGULAR_SHAPES
        #
        self.component_image_on_canvas()
        self.sidebar_settings(
            allowed_shapes=allowed_shapes,
            preview_subject="pixelation / before saving",
        )

    def preview(self):
        """Show a slider allowing to preview the modified video"""
        self.component_image_on_canvas()
        self.sidebar_preview()
        self.sidebar_export()


class PostPanelActions(core.InterfacePlugin):

    """Pre-panel actions for the video GUI in sequential order"""

    def first_frame(self):
        """Cut before the first frame if required"""
        self.vars.kept_frames.update(start=self.tkvars.current_frame.get())
        self.application.cut_video(
            to_=self.vars.kept_frames.start - 1,
        )

    def last_frame(self):
        """Cut after the last frame if required,
        and if the last frame is greater than the first frame
        """
        current_frame = self.tkvars.current_frame.get()
        if current_frame > self.vars.kept_frames.start:
            self.vars.kept_frames.update(end=self.tkvars.current_frame.get())
            self.application.cut_video(
                from_=self.vars.kept_frames.end + 1,
            )
        #

    def start_area(self):
        """Append coordinates (current frame and selection)
        to the stations list
        """
        logging.debug("Saving coordinates ...")
        self.vars.stations.append(self.application.get_coordinates())
        self.vars.update(
            modified_frames=tempfile.TemporaryDirectory(),
        )
        logging.debug("Created tempdir %r", self.vars.modified_frames.name)

    def stop_area(self):
        """Append coordinates (current frame and selection)
        to the stations list
        """
        logging.debug("Saving coordinates ...")
        self.vars.stations.append(self.application.get_coordinates())
        # Set pixelations shape
        logging.debug("Pixelating the segment...")
        [segment_start, segment_end] = self.vars.stations[-2:]
        px_shape = core.SHAPES[segment_start["shape"]]
        if core.SHAPES[segment_end["shape"]] != px_shape:
            raise ValueError(
                "Shapes at both ends of the segment must be the same!"
            )
        #
        pixelator = pixelations.MultiFramePixelation(
            pathlib.Path(self.vars.original_frames.name),
            pathlib.Path(self.vars.modified_frames.name),
            quality="maximum",
        )
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title="Pixelating segment",
            label="Applying pixelation to all frames in the segment…",
            maximum=100,
        )
        for percentage in pixelator.pixelate_segment(
            px_shape,
            segment_start,
            segment_end,
        ):
            progress.set_current_value(percentage)
        #
        progress.action_cancel()
        self.vars.update(unsaved_changes=True)


class Rollbacks(core.InterfacePlugin):

    """Rollback action in order of appearance"""

    def stop_area(self):
        """Actions when clicking the "previous" button
        in the end area selection panel:
        Set frame range for the previous panel.
        Reset frame and position to the ones from the previous panel.
        """
        self.vars.later_stations.append(self.application.get_coordinates())
        self.application.adjust_frame_limits()
        segment_end = self.vars.stations.pop()
        self.application.apply_coordinates(segment_end)
        # Set minimum frame to before-previous panel frame if possible.
        # Clean up the modified_frames temporary directory.
        try:
            segment_start = self.vars.stations[-1]
        except IndexError:
            frame_position = "Pixelation start"
        else:
            start_frame = segment_start["frame"]
            frame_position = "Pixelation stop"
            self.application.adjust_frame_limits(minimum=start_frame)
            # Remove modified frames of the last segment.
            # If that was the only one, remove the modified
            # first frame of that segment as well.
            if len(self.vars.stations) > 1:
                start_frame += 1
            #
            modified_frames_path = pathlib.Path(self.vars.modified_frames.name)
            for frame_number in range(start_frame, segment_end["frame"] + 1):
                frame_file = modified_frames_path / (
                    pixelations.FRAME_PATTERN % frame_number
                )
                try:
                    frame_file.unlink()
                except FileNotFoundError:
                    logging.warning("Frame# %s not found", frame_number)
                #
            #
        #
        logging.debug("Frame position: {frame_position}")
        self.vars.update(
            frame_file=self.vars.frame_file,
            image=pixelations.FramePixelation(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            ),
            frame_position=frame_position,
            trace=True,
        )

    def preview(self):
        """Actions when clicking the "previous" button
        in the preview panel:
        same as in stop_area,
        and reset of the drag action
        """
        if self.vars.panel_stack[-1] in (START_AREA, STOP_AREA):
            self.stop_area()
        #
        self.tkvars.drag_action.set(self.vars.previous_drag_action)


class Validator(core.Validator):

    """Validate user settings"""

    @staticmethod
    def checked_export_crf(export_crf):
        """Check if export_crf is inside the allowd range"""
        minimum_crf = 0
        maximum_crf = 51
        if not isinstance(export_crf, int):
            raise ValueError("Wrong type, must be an integer")
        #
        if export_crf < minimum_crf:
            logging.warning(
                "Adjusted export_crf to minimum (%s)", minimum_crf
            )
            return minimum_crf
        #
        if export_crf > maximum_crf:
            logging.warning(
                "Adjusted export_crf to maximum (%s)", maximum_crf
            )
            return maximum_crf
        #
        return export_crf

    def checked_export_preset(self, export_preset):
        """Check if export_preset is supported"""
        self.must_be_in_collection(
            export_preset,
            EXPORT_PRESETS,
            "Unsupported preset"
        )
        return export_preset

    @staticmethod
    def checked_prefer_include_audio(prefer_include_audio):
        """Check for True or False"""
        if prefer_include_audio not in (True, False):
            raise ValueError("Unsupported value")
        #
        return prefer_include_audio


class VideoUI(core.UserInterface):

    """Modular user interface for video pixelation"""

    phases = PHASES
    panel_names = PANEL_NAMES
    looped_panels = {STOP_AREA}

    script_name = SCRIPT_NAME
    version = VERSION
    copyright_notice = COPYRIGHT_NOTICE

    action_class = Actions
    callback_class = Callbacks
    panel_class = Panels
    post_panel_action_class = PostPanelActions
    rollback_class = Rollbacks
    validator_class = Validator

    default_settings = dict(
        tilesize=10,
        export_crf=18,
        export_preset="ultrafast",
        prefer_include_audio=True,
        **core.DEFAULT_SETTINGS,
    )

    def __init__(self, file_path, options):
        """Initialize the super class"""
        super().__init__(
            file_path,
            options,
            SCRIPT_PATH,
            canvas_width=CANVAS_WIDTH,
            canvas_height=CANVAS_HEIGHT,
        )

    def additional_variables(self):
        """Subclass-specific post-initialization
        (additional variables)
        """
        self.vars.update(
            original_frames=None,
            modified_frames=None,
            nb_frames=None,
            has_audio=False,
            previous_drag_action=core.MOVE_SELECTION,
            frame_position=None,
            frame_file=None,
            frame_rate=None,
            frames_cache=None,
            ffmpeg_loglevel="quiet",
            stations=[],
            later_stations=[],
            duration_usec=None,
            unsaved_changes=False,
            frame_limits=core.Namespace(minimum=1, maximum=1),
            kept_frames=core.Namespace(start=1, end=1),
        )
        if self.options.loglevel == logging.DEBUG:
            self.vars.update(ffmpeg_loglevel="error")
        #
        self.tkvars.update(
            current_frame=self.callbacks.get_traced_intvar("change_frame"),
            current_frame_text=self.callbacks.get_traced_stringvar(
                "change_frame_from_text"
            ),
            end_frame=tkinter.IntVar(),
            export=core.Namespace(
                crf=self.callbacks.get_traced_intvar(
                    "set_export_preferences",
                    value=self.vars.user_settings.export_crf,
                ),
                preset=self.callbacks.get_traced_stringvar(
                    "set_export_preferences",
                    value=self.vars.user_settings.export_preset,
                ),
                include_audio=tkinter.IntVar(),
            ),
        )

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        self.widgets.update(
            frame_canvas=None,
            frames_slider=None,
            frame_number=None,
        )

    def adjust_current_frame(self, new_frame_number=None):
        """Adjust current frame without calling triggers:
        set to frame number if given,
        and fix it if it is outside the allowed range
        """
        previous_trace_setting = self.vars.trace
        self.vars.update(trace=False)
        old_frame_number = self.tkvars.current_frame.get()
        if new_frame_number is None:
            new_frame_number = old_frame_number
        #
        if new_frame_number < self.vars.frame_limits.minimum:
            logging.warning(
                "Raising frame# to minimum (%r)",
                self.vars.frame_limits.minimum,
            )
            new_frame_number = self.vars.frame_limits.minimum
        elif new_frame_number > self.vars.frame_limits.maximum:
            new_frame_number = self.vars.frame_limits.maximum
            logging.warning(
                "Lowering frame# to maximum (%r)",
                self.vars.frame_limits.maximum,
            )
            new_frame_number = self.vars.frame_limits.maximum
        #
        if new_frame_number != old_frame_number:
            logging.debug("Setting frame# to %r", new_frame_number)
            self.tkvars.current_frame.set(new_frame_number)
        #
        # set current_frame_text unconditionally
        self.tkvars.current_frame_text.set(str(new_frame_number))
        self.vars.update(
            frame_file=pixelations.FRAME_PATTERN % new_frame_number,
            trace=previous_trace_setting,
        )

    def adjust_frame_limits(self, minimum=None, maximum=None):
        """Adjust frame limits without being restricted by
        connections of the current_frame and current_frame_text
        control variables to their widgets
        """
        # Destroy pre-existing widgets to remove variable limits set before
        for widget in (self.widgets.frame_number, self.widgets.frames_slider):
            try:
                widget.destroy()
            except AttributeError:
                pass
            #
        #
        self.vars.frame_limits.minimum = minimum or self.vars.kept_frames.start
        self.vars.frame_limits.maximum = maximum or self.vars.kept_frames.end
        self.adjust_current_frame()

    def apply_coordinates(self, coordinates):
        """Apply the provided coordinates:
        Set frame and area
        """
        previous_trace_setting = self.vars.trace
        self.adjust_current_frame(coordinates["frame"])
        self.vars.update(trace=False)
        for (item, value) in coordinates.items():
            try:
                target = self.tkvars.selection[item]
            except KeyError:
                continue
            #
            if not value:
                continue
            #
            logging.debug("Setting selection item %r to %r", item, value)
            target.set(value)
        #
        self.vars.update(trace=previous_trace_setting)

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        file_type = mimetypes.guess_type(str(file_path))[0]
        if not file_type or not file_type.startswith("video/"):
            return False
        #
        return True

    def cut_video(self, from_=None, to_=None):
        """Remove frame files from_ to to_"""
        if from_ is None:
            from_ = 1
        #
        if to_ is None:
            to_ = self.vars.nb_frames
        #
        if to_ < from_:
            logging.debug("No cutting required!")
            return
        #
        original_path = pathlib.Path(self.vars.original_frames.name)
        range_upper = to_ + 1
        logging.debug(
            "Deleting %r files from %s ...",
            range_upper - from_,
            original_path,
        )
        for frame_number in range(from_, range_upper):
            frame_file = pixelations.FRAME_PATTERN % frame_number
            frame_path = original_path / frame_file
            frame_path.unlink()
        #
        logging.debug("... done!")
        self.vars.update(unsaved_changes=True)

    def __examine_video(self, file_path):
        """Examine the video and set the video properties variables"""
        progress = gui.TransientWindow(
            self.main_window, title=f"Loading {file_path.name} (step 1)"
        )
        label = tkinter.Label(progress.body, text="Examining audio stream …")
        label.grid()
        progress.update_idletasks()
        logging.debug("Examining audio stream …")
        has_audio = bool(
            ffmw.get_stream_info(
                file_path,
                ffprobe_executable=self.options.ffprobe_executable,
                select_streams="a",
                show_entries=ffmw.ENTRIES_ALL,
                loglevel=self.vars.ffmpeg_loglevel,
            )
        )
        logging.debug("%r has audio: %r", file_path.name, has_audio)
        self.tkvars.export.include_audio.set(
            int(has_audio and self.vars.user_settings.prefer_include_audio)
        )
        self.vars.update(has_audio=has_audio)
        label = tkinter.Label(progress.body, text="Examining video stream …")
        label.grid()
        progress.update_idletasks()
        logging.debug("Examining video stream …")
        video_properties = ffmw.get_stream_info(
            file_path,
            ffprobe_executable=self.options.ffprobe_executable,
            select_streams="v",
            loglevel=self.vars.ffmpeg_loglevel,
        )
        # Validate video properties,
        # especially nb_frames, duration and frame rates
        nb_frames = None
        frame_rate = None
        duration_usec = None
        try:
            nb_frames = int(video_properties["nb_frames"])
            frame_rate = Fraction(video_properties["avg_frame_rate"])
            duration_usec = float(video_properties["duration"]) * ONE_MILLION
        except ValueError as error:
            logging.warning(error)
            video_data = ffmw.count_all_frames(
                file_path,
                ffmpeg_executable=self.options.ffmpeg_executable,
                loglevel=self.vars.ffmpeg_loglevel,
            )
            nb_frames = int(video_data["frame"])
            duration_usec = int(video_data["out_time_us"])
            frame_rate = Fraction(nb_frames * ONE_MILLION, duration_usec)
        finally:
            progress.action_cancel()
        #
        if nb_frames > MAX_NB_FRAMES:
            raise ValueError(f"To many frames (maximum is {MAX_NB_FRAMES})!")
        #
        logging.debug("Duration (usec): %r", duration_usec)
        if frame_rate.denominator > 1001:
            logging.debug("Original frame rate: %s", frame_rate)
            frame_rate = frame_rate.limit_denominator(100)
        #
        logging.debug("Frame rate: %s", frame_rate)
        logging.debug("Number of frames: %s", nb_frames)
        self.vars.update(
            duration_usec=duration_usec,
            frame_rate=frame_rate,
            nb_frames=nb_frames,
        )

    def get_coordinates(self):
        """Get current coordinates (frame and selection)
        as a dict
        """
        coordinates = dict(EMPTY_SELECTION)
        current_frame = self.tkvars.current_frame.get()
        logging.debug(" - Current frame#: %r", current_frame)
        coordinates["frame"] = current_frame
        for key, variable in self.tkvars.selection.items():
            value = variable.get()
            logging.debug(" - selection item %r: %r", key, value)
            coordinates[key] = variable.get()
        #
        # Respect quadratic shapes
        if coordinates["shape"] in core.QUADRATIC_SHAPES:
            logging.debug(
                " - [quadratic] height: %(height)r -> %(width)r",
                coordinates,
            )
            coordinates["height"] = coordinates["width"]
        #
        return coordinates

    def load_file(self, file_path):
        """Load the file. Wrap self.__load_video
        to transform a subprocess.CalledProcessError to a ValueError
        """
        try:
            self.__examine_video(file_path)
            self.__split_video(file_path)
        except subprocess.CalledProcessError as error:
            raise ValueError(str(error)) from error
        #

    def play_flipbook(self):
        """Play current video as a flipbook"""
        raise NotImplementedError

    def pre_quit_check(
        self,
    ):
        """Checks and actions before exiting the application"""
        self.execute_post_panel_action()
        if self.vars.unsaved_changes:
            if messagebox.askyesno("Unsaved Changes", "Save your changes?"):
                if not self.save_file():
                    if not messagebox.askokcancel(
                        "Changes not saved!",
                        "Really exit without saving?",
                        default=messagebox.CANCEL,
                    ):
                        return False
                    #
                #
            #
        #
        for tempdir in (self.vars.original_frames, self.vars.modified_frames):
            try:
                tempdir.cleanup()
                logging.debug("Deleted temporary directory %s", tempdir.name)
            except AttributeError:
                pass
            #
        #
        return True

    def resize_selection(self, width=None, height=None):
        """Change selection size only in the suitable panels"""
        if self.vars.current_panel in (START_AREA, STOP_AREA):
            super().resize_selection(width=width, height=height)
        #

    def save_and_exit(self):
        """Save and exit"""
        self.save_file()
        self.quit()

    def save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        self.execute_post_panel_action()
        if self.vars.current_panel != PREVIEW:
            if self.tkvars.show_preview.get():
                self.vars.panel_stack.append(self.vars.current_panel)
                self.jump_to_panel(PREVIEW)
                return False
            #
            self.__show_export_settings_dialog()
        #
        original_suffix = self.vars.original_path.suffix
        self.vars.update(disable_key_events=True)
        selected_file = filedialog.asksaveasfilename(
            initialdir=str(self.vars.original_path.parent),
            defaultextension=original_suffix,
            parent=self.main_window,
            title="Save pixelated video as…",
        )
        self.vars.update(disable_key_events=False)
        if not selected_file:
            return False
        #
        logging.debug("Saving the file as %r", selected_file)
        #  save the file and reset the "touched" flag
        # self.vars.image.original.save(selected_file)
        file_path = pathlib.Path(selected_file)
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title="Saving video",
            label=f"Saving as {file_path.name} …",
            maximum=self.vars.nb_frames,
        )
        # Build the video from the frames
        with TemporaryFramesPath(self) as temp_frames_path:
            cut_at_start = self.vars.kept_frames.start - 1
            arguments = [
                "-framerate",
                str(self.vars.frame_rate),
                "-i",
                str(temp_frames_path / pixelations.FRAME_PATTERN),
            ]
            if self.tkvars.export.include_audio.get():
                if cut_at_start:
                    arguments.extend(
                        [
                            "-ss",
                            "%.3f"
                            % float(cut_at_start / self.vars.frame_rate),
                        ]
                    )
                #
                arguments.extend(
                    [
                        "-i",
                        str(self.vars.original_path),
                        "-map",
                        "0:v",
                        "-map",
                        "1:a",
                        "-c:a",
                        "copy",
                    ]
                )
                cut_at_end = self.vars.nb_frames - self.vars.kept_frames.end
                if cut_at_start or cut_at_end:
                    arguments.append("-shortest")
                #
            #
            if self.tkvars.crop.get():
                crop_area = self.vars.crop_area
                width = crop_area.right - crop_area.left
                height = crop_area.bottom - crop_area.top
                crop_filter = (
                    f"crop=w={width}:h={height}:"
                    f"x={crop_area.left}:y={crop_area.top},"
                )
            else:
                crop_filter = ""
            #
            arguments.extend(
                [
                    "-c:v",
                    "libx264",
                    "-preset",
                    self.tkvars.export.preset.get(),
                    "-crf",
                    str(self.tkvars.export.crf.get()),
                    "-vf",
                    f"fps={self.vars.frame_rate},{crop_filter}format=yuv420p",
                    "-y",
                    str(file_path),
                ]
            )
            save_exec = ffmw.FFmpegWrapper(
                *arguments, executable=self.options.ffmpeg_executable
            )
            save_exec.add_extra_arguments(
                "-loglevel", self.vars.ffmpeg_loglevel
            )
            try:
                for line in save_exec.stream(check=True):
                    if line.startswith("frame="):
                        value = line.split("=", 1)[1]
                        progress.set_current_value(int(value))
                    #
                #
            finally:
                progress.action_cancel()
            #
        #
        if not self.__show_in_default_player(str(file_path)):
            messagebox.showinfo(
                "Video saved",
                f"The video has been saved as {file_path}",
                icon=messagebox.INFO,
                parent=self.main_window,
            )
        #
        self.vars.unsaved_changes = False
        return True

    def show_additional_buttons(self, buttons_area):
        """Additional buttons for the pixelate_image script"""
        buttonstates = dict(
            cut_end=tkinter.DISABLED,
            add_route=tkinter.DISABLED,
            add_segment=tkinter.DISABLED,
            back=tkinter.DISABLED,
            save=tkinter.NORMAL,
            save_and_exit=tkinter.NORMAL,
        )
        commands = dict(
            cut_end=self.next_panel,
            add_route=self.start_new_route,
            add_segment=self.next_panel,
            back=self.previous_panel,
            save=self.save_file,
            save_and_exit=self.save_and_exit,
        )
        button_texts = dict(
            cut_end="Cut end",
            add_route="Add new route",
            add_segment="Add connected segment",
            back="\u25c1 Back",
            save="Save",
            save_and_exit="Save and exit",
        )
        if self.vars.current_panel == FIRST_FRAME:
            buttonstates.update(
                cut_end=tkinter.NORMAL,
                add_route=tkinter.NORMAL,
            )
        elif self.vars.current_panel == LAST_FRAME:
            buttonstates.update(add_route=tkinter.NORMAL)
            commands.update(add_route=self.next_panel)
        elif self.vars.current_panel == START_AREA:
            buttonstates.update(add_segment=tkinter.NORMAL)
            button_texts.update(add_segment="Add segment end")
        elif self.vars.current_panel in (STOP_AREA, PREVIEW):
            buttonstates.update(
                add_route=tkinter.NORMAL,
                add_segment=tkinter.NORMAL,
                back=tkinter.NORMAL,
            )
        #
        buttons = core.Namespace(
            (
                button_id,
                tkinter.Button(
                    buttons_area,
                    text=text,
                    state=buttonstates[button_id],
                    command=commands[button_id],
                ),
            )
            for (button_id, text) in button_texts.items()
        )
        buttons.cut_end.grid(row=0, column=0, **core.BUTTONS_GRID_E)
        buttons.add_route.grid(
            row=0, column=1, columnspan=2, **core.BUTTONS_GRID_W
        )
        buttons.back.grid(row=1, column=0, **core.BUTTONS_GRID_E)
        buttons.add_segment.grid(
            row=1, column=1, columnspan=2, **core.BUTTONS_GRID_W
        )
        buttons.save.grid(row=2, column=0, **core.BUTTONS_GRID_E)
        buttons.save_and_exit.grid(
            row=2, column=1, columnspan=2, **core.BUTTONS_GRID_W
        )
        if self.vars.current_panel == PREVIEW:
            # Disable right mouse click as shortcut for "Next"
            self.main_window.unbind_all("<ButtonRelease-3>")
        else:
            # Enable right mouse click as shortcut for "Next"
            self.main_window.bind_all("<ButtonRelease-3>", self.next_panel)
        #
        self.main_window.bind_all("<Left>", self.callbacks.frame_decrement)
        self.main_window.bind_all("<Right>", self.callbacks.frame_increment)
        self.vars.update(trace=True)
        return 3

    def __show_export_settings_dialog(self):
        """Show export settings in a modal dialog and wait for the window"""
        export_settings = gui.TransientWindowWithButtons(
            self.main_window, title="Export settings"
        )
        self.panels.component_export_settings(
            export_settings.body, parent_window=export_settings
        )
        export_settings.create_buttonbox(cancel_button=False)
        self.main_window.wait_window(export_settings)

    def show_image(self):
        """Show image or preview according to the show_preview setting,
        but only in the start_area or stop_area panels.
        """
        if self.vars.current_panel not in (START_AREA, STOP_AREA):
            return
        #
        super().show_image()

    def __show_in_default_player(self, full_file_name):
        """If showing the video in the default player is possible,
        ask to do that (and do it after a positive answer).
        Return True if it is possible, False if not.
        """
        show_video_command = "xdg-open"
        shell = False
        if sys.platform == "win32":
            show_video_command = "start"
            shell = True
        else:
            try:
                subprocess.run(
                    (show_video_command, "--version"),
                    stderr=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
            except subprocess.CalledProcessError:
                return False
            #
        #
        show_video = messagebox.askyesno(
            "Video saved",
            "Show the video in your default player now?",
            icon=messagebox.QUESTION,
            parent=self.main_window,
        )
        if show_video:
            subprocess.run(
                (show_video_command, full_file_name),
                shell=shell,
                stderr=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                check=True,
            )
        #
        return True

    def __split_video(self, file_path):
        """Split the video into frames,
        showing a progress bar (in an auto-closing modal window)
        """
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title="Loading video",
            label=f"Splitting {file_path.name} into frames …",
            maximum=self.vars.nb_frames,
        )
        # Create a temorary directory for original frames
        self.vars.update(original_frames=tempfile.TemporaryDirectory())
        logging.debug("Created tempdir %r", self.vars.original_frames.name)
        # Split into frames
        split_exec = ffmw.FFmpegWrapper(
            "-i",
            str(file_path),
            "-qscale:v",
            "1",
            "-qmin",
            "1",
            os.path.join(
                self.vars.original_frames.name, pixelations.FRAME_PATTERN
            ),
            executable=self.options.ffmpeg_executable,
        )
        split_exec.add_extra_arguments("-loglevel", self.vars.ffmpeg_loglevel)
        try:
            for line in split_exec.stream(check=True):
                if line.startswith("frame="):
                    value = line.split("=", 1)[1]
                    progress.set_current_value(int(value))
                #
            #
        finally:
            progress.action_cancel()
        #
        # set the original path and displayed file name
        self.vars.update(original_path=file_path, unsaved_changes=False)
        self.vars.kept_frames.update(start=1, end=self.vars.nb_frames)
        self.vars.stations.clear()
        self.vars.later_stations.clear()
        self.tkvars.file_name.set(file_path.name)
        self.tkvars.current_frame.set(1)

    def start_new_route(self):
        """Apply changes to the frames,
        and re-cycle them as original frames
        """
        logging.debug("Executing post-panel action")
        self.execute_post_panel_action()
        if self.vars.modified_frames:
            logging.debug("Setting modified frames as originals")
            original_frames_path = pathlib.Path(self.vars.original_frames.name)
            modified_frames_path = pathlib.Path(self.vars.modified_frames.name)
            for frame_path in modified_frames_path.glob("*"):
                frame_file_name = frame_path.name
                logging.debug("Moving %r to originals path", frame_file_name)
                frame_path.rename(original_frames_path / frame_file_name)
            #
            # Implicit cleanup by garbage collection
            # self.vars.modified_frames.cleanup()
            self.vars.update(modified_frames=None)
        #
        self.vars.stations.clear()
        self.vars.later_stations.clear()
        # Push current coordinates to self.vars.later_stations for re-use
        if self.vars.current_panel in (STOP_AREA, PREVIEW):
            self.vars.later_stations.append(self.get_coordinates())
        #
        # Directly jump to start_area
        self.vars.panel_stack.append(self.vars.current_panel)
        self.jump_to_panel(START_AREA)


#
# Functions
#


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description="Pixelate parts of a schort video clip"
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
    argument_parser.add_argument(
        "--ffmpeg-executable",
        default=ffmw.FFMPEG,
        help="ffmpeg executable (default: %(default)s)",
    )
    argument_parser.add_argument(
        "--ffprobe-executable",
        default=ffmw.FFPROBE,
        help="ffprobe executable (default: %(default)s)",
    )
    argument_parser.add_argument(
        "image_file",
        nargs="?",
        type=pathlib.Path,
        help="A video file. If none is provided,"
        " the script will ask for a file.",
    )
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    logging.basicConfig(
        format="%(levelname)-8s\u2551 %(funcName)s @ L%(lineno)s"
        " → %(message)s",
        level=arguments.loglevel,
    )
    selected_file = arguments.image_file
    if selected_file and not selected_file.is_file():
        selected_file = None
    #
    VideoUI(selected_file, arguments)


if __name__ == "__main__":
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
