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
except OSError as error:
    VERSION = "(Version file is missing: %s)" % error
#

# Phases
OPEN_FILE = core.UserInterface.phase_open_file
START_FRAME = "start_frame"
START_AREA = "start_area"
END_FRAME = "end_frame"
END_AREA = "end_area"
PREVIEW = "preview"

PHASES = (
    OPEN_FILE,
    START_FRAME,
    START_AREA,
    END_FRAME,
    END_AREA,
    PREVIEW,
)

PANEL_NAMES = {
    START_FRAME: "Select pixelation start frame",
    START_AREA: "Select pixelation start area",
    END_FRAME: "Select pixelation end frame",
    END_AREA: "Select pixelation end area",
    PREVIEW: "Preview the video stream",
}

EMPTY_SELECTION = dict(
    frame=None,
    shape=None,
    px_shape=None,
    center_x=None,
    center_y=None,
    width=None,
    height=None,
)

MAX_NB_FRAMES = 10000

ONE_MILLION = 1000000

DEFAULT_EXPORT_CRF = 18
DEFAULT_EXPORT_PRESET = "slow"

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
CANVAS_HEIGHT = 576

DEFAULT_TILESIZE = 10


#
# Classes
#


class Actions(core.InterfacePlugin):

    """Pre-panel actions for the video GUI in sequential order"""

    def start_frame(self):
        """Actions before showing the start frame selection panel:
        Set frame range from the first to the last but 5th frame.
        """
        self.ui_instance.adjust_frame_limits(maximum=self.vars.nb_frames - 5)

    def start_area(self):
        """Actions before showing the start area selection panel:
        Fix the selected frame as start frame.
        Load the frame and set the variables
        """
        self.vars.start_at.frame = self.tkvars.current_frame.get()
        logging.debug("Current frame# is %r", self.vars.start_at.frame)
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
        )
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        #
        # Set selection (pre-configured or empty)
        self.ui_instance.adjust_selection(self.vars.end_at)
        (im_width, im_height) = self.vars.image.original.size
        sel_width = self.tkvars.selection.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width
            sel_width = max(core.INITIAL_SELECTION_SIZE, round(im_width / 5))
        #
        sel_height = self.tkvars.selection.height.get()
        if not sel_height:
            sel_height = sel_width
        #
        center_x = self.tkvars.selection.center_x.get() or im_width // 2
        center_y = self.tkvars.selection.center_y.get() or im_height // 2
        self.ui_instance.update_selection(
            center_x=center_x,
            center_y=center_y,
            width=min(sel_width, im_width),
            height=min(sel_height, im_height),
            shape=self.tkvars.selection.shape.get() or core.OVAL,
            tilesize=self.tkvars.selection.tilesize.get() or DEFAULT_TILESIZE,
        )
        self.tkvars.drag_action.set(self.vars.previous_drag_action)
        # set the show_preview variable by default
        self.tkvars.show_preview.set(1)

    def end_frame(self):
        """Actions before showing the end frame selection panel:
        Set frame range from the selected start frame
        to the last frame.
        Fix the selected start coordinates
        """
        self.ui_instance.adjust_frame_limits(
            minimum=self.vars.start_at.frame + 1
        )
        if self.vars.end_at.frame:
            self.ui_instance.adjust_current_frame(self.vars.end_at.frame)
        #
        logging.debug("Fix start coordinates:")
        self.ui_instance.store_selection(self.vars.start_at)

    def end_area(self):
        """Actions before showing the end area selection panel:
        Fix the selected frame as end frame.
        Load the frame for area selection
        """
        self.vars.end_at.frame = self.tkvars.current_frame.get()
        logging.debug("Current frame# is %r", self.vars.end_at.frame)
        self.ui_instance.adjust_selection(self.vars.end_at)
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
        )
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        #

    def preview(self):
        """Actions before showing the preview panel:
        Fix the selected end coordinates
        Apply the pixelations to all images
        """
        logging.debug("Fix end coordinates:")
        self.ui_instance.store_selection(self.vars.end_at)
        #
        # Save pixelation start frame
        self.vars.opxsf.append(self.vars.start_at.frame)
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        # Set pixelations shape
        px_shape = core.SHAPES[self.vars.start_at.shape]
        if px_shape != core.SHAPES[self.vars.end_at.shape]:
            raise ValueError("Shapes at start and end must be the same!")
        #
        self.vars.modified_frames = tempfile.TemporaryDirectory()
        logging.info("Created tempdir %r", self.vars.modified_frames.name)
        pixelator = pixelations.MultiFramePixelation(
            pathlib.Path(self.vars.original_frames.name),
            pathlib.Path(self.vars.modified_frames.name),
            quality="maximum",
        )
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title="Applying pixelation",
            label="Applying pixelation to selected frames …",
            maximum=100,
        )
        for percentage in pixelator.pixelate_frames(
            self.tkvars.selection.tilesize.get(),
            px_shape,
            self.vars.start_at,
            self.vars.end_at,
        ):
            progress.set_current_value(percentage)
        #
        progress.action_cancel()
        self.vars.unsaved_changes = True
        self.ui_instance.adjust_frame_limits()
        self.vars.previous_drag_action = self.tkvars.drag_action.get()
        self.tkvars.drag_action.set(core.NEW_CROP_AREA)


class VideoCallbacks(core.Callbacks):

    """Callback functions for the video UI"""

    def change_frame(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        try:
            self.widgets.canvas.delete("vframe")
        except AttributeError as error:
            logging.warning("%s", error)
        except tkinter.TclError as error:
            logging.warning("%s", error)
            return
        #
        current_frame = self.tkvars.current_frame.get()
        # logging.debug('Current frame# is %r', current_frame)
        if current_frame < self.vars.frame_limits.minimum:
            current_frame = self.vars.frame_limits.minimum
            logging.warning(
                "Raising current frame to minimum (%r)", current_frame
            )
        elif current_frame > self.vars.frame_limits.maximum:
            current_frame = self.vars.frame_limits.maximum
            logging.warning(
                "Lowering current frame to maximum (%r)", current_frame
            )
        #
        self.vars.trace = False
        self.tkvars.current_frame_text.set(str(current_frame))
        if current_frame != self.tkvars.current_frame.get():
            self.tkvars.current_frame.set(current_frame)
        #
        self.vars.trace = True
        self.vars.frame_file = pixelations.FRAME_PATTERN % current_frame
        frame_path = (
            pathlib.Path(self.vars.original_frames.name) / self.vars.frame_file
        )
        if self.vars.current_panel == PREVIEW:
            modified_path = (
                pathlib.Path(self.vars.modified_frames.name)
                / self.vars.frame_file
            )
            if modified_path.is_file():
                frame_path = modified_path
            #
        #
        self.vars.vframe = pixelations.BaseImage(
            frame_path,
            canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
        )
        if self.tkvars.crop.get():
            self.vars.vframe.set_crop_area(self.vars.crop_area)
        #
        self.vars.tk_image = self.vars.vframe.tk_original
        self.widgets.canvas.create_image(
            0, 0, image=self.vars.tk_image, anchor=tkinter.NW, tags="vframe"
        )

    def change_frame_from_text(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        self.tkvars.current_frame.set(
            int(self.tkvars.current_frame_text.get())
        )
        #

    def toggle_crop_display(self, *unused_arguments):
        """Toggle crop area preview update"""
        if not self.vars.trace:
            return
        #
        if self.vars.current_panel in (PREVIEW, START_FRAME, END_FRAME):
            self.change_frame()
            return
        #
        super().toggle_crop_display(*unused_arguments)

    def update_buttons(self, *unused_arguments):
        """Trigger previous, next and save button states changes"""
        for (button_name, state_var) in self.tkvars.buttonstate.items():
            gui.set_state(self.widgets.buttons[button_name], state_var.get())
        #


class Panels(core.Panels):

    """Panels and panel components"""

    # Components

    def component_frames_slider(self, image_frame, frame_position):
        """Show a slider in the image frame"""
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
            label=f"{frame_position} frame:",
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame,
        )
        self.widgets.frames_slider.grid()
        logging.debug("Showing canvas")
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=self.vars.canvas_width,
            height=self.vars.canvas_height,
        )
        self.widgets.canvas.grid()
        self.vars.trace = True
        if self.vars.current_panel == PREVIEW:
            # add bindings (for crop area definition)
            self.widgets.canvas.bind(
                "<ButtonPress-1>", self.ui_instance.callbacks.drag_start
            )
            self.widgets.canvas.bind(
                "<ButtonRelease-1>", self.ui_instance.callbacks.drag_stop
            )
            self.widgets.canvas.bind(
                "<B1-Motion>", self.ui_instance.callbacks.drag_move
            )
            # Set the canvas cursor
            self.ui_instance.callbacks.set_canvas_cursor()
        #
        self.ui_instance.callbacks.change_frame()

    def component_frameselection(self, position):
        """Select the start or end frame using a slider
        abd show that frame on a canvas
        """
        # logging.debug(
        #     '%s frame# is %r', position, self.tkvars.current_frame.get())
        image_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_frames_slider(image_frame, position)
        image_frame.grid(row=1, column=0, rowspan=3, **core.GRID_FULLWIDTH)
        self.sidebar_frameselection(position)
        # logging.debug(
        #     '%s frame# is %r', position, self.tkvars.current_frame.get())

    def component_add_another(self, sidebar_frame):
        """Section with the 'Add another pixelation' button"""
        self.ui_instance.heading_with_help_button(
            sidebar_frame, "More pixelations"
        )
        more_button = tkinter.Button(
            sidebar_frame,
            text="Add another pixelation",
            command=self.ui_instance.apply_and_recycle,
        )
        more_button.grid(sticky=tkinter.W, columnspan=4)

    def component_export_settings(self, sidebar_frame):
        """Section with the export settings"""
        # Disabe "include audio" if the original video
        # has no audio stream
        if self.vars.has_audio:
            self.tkvars.export.include_audio.set(1)
            include_audio_state = tkinter.NORMAL
        else:
            self.tkvars.export.include_audio.set(0)
            include_audio_state = tkinter.DISABLED
        #
        self.ui_instance.heading_with_help_button(
            sidebar_frame, "Export settings"
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
            columnspan=3,
        )
        include_audio = tkinter.Checkbutton(
            sidebar_frame,
            anchor=tkinter.W,
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

    def component_image_info(
        self, parent_frame, frame_position, change_enabled=False
    ):
        """Show information about the current video frame"""
        self.ui_instance.heading_with_help_button(
            parent_frame, f"{frame_position} frame"
        )
        label = tkinter.Label(parent_frame, text="Number:")
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frame_number.destroy()
        except AttributeError:
            pass
        #
        if change_enabled:
            self.widgets.frame_number = tkinter.Spinbox(
                parent_frame,
                from_=self.vars.frame_limits.minimum,
                to=self.vars.frame_limits.maximum,
                textvariable=self.tkvars.current_frame_text,
                state="readonly",
                width=4,
            )
        else:
            self.widgets.frame_number = tkinter.Label(
                parent_frame, textvariable=self.tkvars.current_frame_text
            )
        #
        label.grid(sticky=tkinter.W)
        self.widgets.frame_number.grid(
            sticky=tkinter.W,
            columnspan=3,
            column=1,
            row=gui.grid_row_of(label),
        )
        self.component_zoom_factor(
            parent_frame, self.vars.vframe.display_ratio
        )
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

    def sidebar_frameselection(self, frame_position):
        """Show the settings frame"""
        frameselection_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_file_info(frameselection_frame)
        self.component_image_info(
            frameselection_frame, frame_position, change_enabled=True
        )
        # self.component_drag_options(frameselection_frame)
        frameselection_frame.columnconfigure(4, weight=100)
        frameselection_frame.grid(
            row=0, column=1, rowspan=2, **core.GRID_FULLWIDTH
        )

    # Panels in order of appearance

    def start_frame(self):
        """Select the start frame using a slider
        and show that frame on a canvas
        """
        self.component_frameselection("Start")

    def start_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.component_select_area("Start")

    def end_frame(self):
        """Select the end frame using a slider
        and show that frame on a canvas
        """
        self.component_frameselection("End")

    def end_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        if self.vars.start_at.shape in core.ELLIPTIC_SHAPES:
            allowed_shapes = core.ELLIPTIC_SHAPES
        else:
            allowed_shapes = core.RECTANGULAR_SHAPES
        #
        self.component_select_area("End", allowed_shapes=allowed_shapes)

    def preview(self):
        """Show a slider allowing to preview the modified video"""
        image_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_frames_slider(image_frame, "Current")
        image_frame.grid(row=1, column=0, rowspan=3, **core.GRID_FULLWIDTH)
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area, **core.WITH_BORDER
        )
        self.component_file_info(sidebar_frame)
        self.component_image_info(
            sidebar_frame, "Current", change_enabled=True
        )
        self.component_add_another(sidebar_frame)
        self.component_export_settings(sidebar_frame)
        self.component_select_drag_action(
            sidebar_frame, supported_actions=[core.NEW_CROP_AREA]
        )
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(row=0, column=1, rowspan=2, **core.GRID_FULLWIDTH)


class Rollbacks(core.InterfacePlugin):

    """Rollback acction in order of appearance"""

    def start_area(self):
        """Actions when clicking the "previous" button
        in the start area selection panel: None
        """
        logging.debug(
            "%s frame# is %r", "Start", self.tkvars.current_frame.get()
        )

    def end_frame(self):
        """Actions when clicking the "previous" button
        in the end_frame selection panel:
        Set frame range from the first to the last but 5th frame.
        Reset the current frame to the saved start frame
        """
        self.ui_instance.adjust_frame_limits(maximum=self.vars.nb_frames - 5)
        self.vars.trace = False
        current_frame = self.vars.start_at.frame
        self.ui_instance.adjust_current_frame(current_frame)
        self.vars.frame_file = pixelations.FRAME_PATTERN % current_frame
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
        )
        #
        self.ui_instance.adjust_selection(self.vars.start_at)
        self.vars.trace = True

    def end_area(self):
        """Actions when clicking the "previous" button
        in the end area selection panel: None
        """
        logging.debug(
            "%s frame# is %r", "End", self.tkvars.current_frame.get()
        )

    def preview(self):
        """Actions when clicking the "previous" button
        in the preview panel:
        Reset the current frame to the saved end frame
        Set the seclection to the selected end coordinates
        Cleanup the modified_frames tempdir
        """
        self.ui_instance.adjust_frame_limits(
            minimum=self.vars.start_at.frame + 1
        )
        self.vars.trace = False
        current_frame = self.vars.end_at.frame
        self.ui_instance.adjust_current_frame(current_frame)
        self.vars.frame_file = pixelations.FRAME_PATTERN % current_frame
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
        )
        #
        self.ui_instance.adjust_selection(self.vars.end_at)
        self.vars.trace = True
        self.vars.opxsf.pop()
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        self.vars.modified_frames.cleanup()
        self.tkvars.drag_action.set(self.vars.previous_drag_action)


class VideoUI(core.UserInterface):

    """Modular user interface for video pixelation"""

    phases = PHASES
    panel_names = PANEL_NAMES
    script_name = SCRIPT_NAME
    version = VERSION
    copyright_notice = COPYRIGHT_NOTICE

    action_class = Actions
    callback_class = VideoCallbacks
    panel_class = Panels
    rollback_class = Rollbacks

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
            vframe=None,
            # List of pixelation start frames
            # (original sequence, and sorted unique)
            opxsf=[],
            spxsf=[],
            previous_drag_action=core.MOVE_SELECTION,
            frame_rate=None,
            frames_cache=None,
            duration_usec=None,
            unsaved_changes=False,
            frame_limits=core.Namespace(minimum=1, maximum=1),
            start_at=core.Namespace(**EMPTY_SELECTION),
            end_at=core.Namespace(**EMPTY_SELECTION),
        )
        self.tkvars.update(
            current_frame=self.callbacks.get_traced_intvar("change_frame"),
            current_frame_text=self.callbacks.get_traced_stringvar(
                "change_frame_from_text"
            ),
            end_frame=tkinter.IntVar(),
            export=core.Namespace(
                crf=tkinter.IntVar(),
                include_audio=tkinter.IntVar(),
                preset=tkinter.StringVar(),
            ),
            buttonstate=core.Namespace(
                previous=self.callbacks.get_traced_stringvar(
                    "update_buttons", value=tkinter.DISABLED
                ),
                next_=self.callbacks.get_traced_stringvar(
                    "update_buttons", value=tkinter.NORMAL
                ),
                save=self.callbacks.get_traced_stringvar(
                    "update_buttons", value=tkinter.DISABLED
                ),
            ),
        )
        self.tkvars.export.crf.set(DEFAULT_EXPORT_CRF)
        self.tkvars.export.preset.set(DEFAULT_EXPORT_PRESET)

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        self.widgets.update(
            buttons=core.Namespace(previous=None, next_=None, more=None),
            frame_canvas=None,
            frames_slider=None,
            frame_number=None,
        )

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        file_type = mimetypes.guess_type(str(file_path))[0]
        if not file_type or not file_type.startswith("video/"):
            return False
        #
        return True

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
            )
        )
        logging.info("%r has audio: %r", file_path.name, has_audio)
        self.vars.has_audio = has_audio
        label = tkinter.Label(progress.body, text="Examining video stream …")
        label.grid()
        progress.update_idletasks()
        logging.debug("Examining video stream …")
        video_properties = ffmw.get_stream_info(
            file_path,
            ffprobe_executable=self.options.ffprobe_executable,
            select_streams="v",
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
                file_path, ffmpeg_executable=self.options.ffmpeg_executable
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
        self.vars.duration_usec = duration_usec
        self.vars.frame_rate = frame_rate
        self.vars.nb_frames = nb_frames

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
        self.vars.original_frames = tempfile.TemporaryDirectory()
        logging.info("Created tempdir %r", self.vars.original_frames.name)
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
        split_exec.add_extra_arguments("-loglevel", "error")
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
        # Clear selection
        self.vars.start_at = core.Namespace(**EMPTY_SELECTION)
        self.vars.end_at = core.Namespace(**EMPTY_SELECTION)
        # set the original path and displayed file name
        self.vars.original_path = file_path
        self.tkvars.file_name.set(file_path.name)
        self.vars.unsaved_changes = False

    def show_additional_buttons(self, buttons_area, buttons_grid):
        """Additional buttons for the pixelate_image script"""
        self.widgets.buttons.previous = tkinter.Button(
            buttons_area, text="\u25c1 Previous", command=self.previous_panel
        )
        self.widgets.buttons.previous.grid(row=0, column=0, **buttons_grid)
        self.widgets.buttons.next_ = tkinter.Button(
            buttons_area, text="\u25b7 Next", command=self.next_panel
        )
        self.widgets.buttons.next_.grid(row=0, column=1, **buttons_grid)
        try:
            self.widgets.buttons.save = tkinter.Button(
                buttons_area, text="\U0001f5ab Save", command=self.save_file
            )
        except tkinter.TclError:
            self.widgets.buttons.save = tkinter.Button(
                buttons_area, text="\u2386 Save", command=self.save_file
            )
        #
        self.widgets.buttons.save.grid(row=0, column=2, **buttons_grid)
        # Set button states and defer state manipulations
        self.vars.trace = False
        if self.vars.current_panel == PREVIEW:
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
            self.tkvars.buttonstate.next_.set(tkinter.DISABLED)
        else:
            self.tkvars.buttonstate.save.set(tkinter.DISABLED)
            self.tkvars.buttonstate.next_.set(tkinter.NORMAL)
        #
        if self.vars.current_panel == START_FRAME:
            self.tkvars.buttonstate.previous.set(tkinter.DISABLED)
        else:
            self.tkvars.buttonstate.previous.set(tkinter.NORMAL)
        #
        self.vars.trace = True
        self.callbacks.update_buttons()
        return 1

    def adjust_current_frame(self, new_current_frame):
        """Adjust current frame without calling triggers"""
        previous_trace_setting = self.vars.trace
        self.vars.trace = False
        logging.debug("Setting current frame# to %r", new_current_frame)
        self.tkvars.current_frame.set(new_current_frame)
        self.tkvars.current_frame_text.set(str(new_current_frame))
        self.vars.trace = previous_trace_setting

    def adjust_frame_limits(self, minimum=None, maximum=None):
        """Adjust frame limits without being restricted by
        connections of the current_frame and current_frame_text
        control variables to their its widgets
        """
        # Destroy pre-existing widgets to remove variable limits set before
        for widget in (self.widgets.frame_number, self.widgets.frames_slider):
            try:
                widget.destroy()
            except AttributeError:
                pass
            #
        #
        self.vars.frame_limits.minimum = minimum or 1
        self.vars.frame_limits.maximum = maximum or self.vars.nb_frames

    def clear_selection(self, storage_vars):
        """Clear selection in storage_vars"""
        for item in storage_vars:
            try:
                self.tkvars.selection[item]
            except KeyError:
                continue
            #
            value = storage_vars[item]
            logging.debug("Clearing selection item %r (was %r)", item, value)
            storage_vars[item] = None
        #

    def store_selection(self, storage_vars):
        """Store selection in storage_vars"""
        for item in storage_vars:
            try:
                source = self.tkvars.selection[item]
            except KeyError:
                continue
            #
            value = source.get()
            logging.debug("Storing selection item %r: %r", item, value)
            storage_vars[item] = value
        #
        # Respect quadratic shapes
        if storage_vars["shape"] in core.QUADRATIC_SHAPES:
            storage_vars["height"] = storage_vars["width"]
        #

    def adjust_selection(self, new_selection_vars):
        """Adjust selection without calling triggers"""
        previous_trace_setting = self.vars.trace
        self.vars.trace = False
        for (item, value) in new_selection_vars.items():
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
        self.vars.trace = previous_trace_setting

    def apply_and_recycle(self):
        """Apply changes to the frames,
        and re-cycle them as original frames
        """
        logging.debug("Applying changes and reusing the frames")
        # fill up "modified" directory with missing frames
        self.complete_modified_directory()
        #
        self.vars.original_frames.cleanup()
        self.vars.original_frames = self.vars.modified_frames
        self.vars.modified_frames = None
        # self.vars.trace = False
        # Clear end selection
        self.clear_selection(self.vars.end_at)
        #
        self.vars.current_panel = OPEN_FILE
        self.next_panel()

    def complete_modified_directory(self):
        """Fill up modified directory from souce directory"""
        original_path = pathlib.Path(self.vars.original_frames.name)
        target_path = pathlib.Path(self.vars.modified_frames.name)
        for frame_number in range(1, self.vars.nb_frames + 1):
            frame_file = pixelations.FRAME_PATTERN % frame_number
            frame_target_path = target_path / frame_file
            if not frame_target_path.exists():
                frame_source_path = original_path / frame_file
                frame_source_path.rename(frame_target_path)
            #
        #

    def jump_next_px(self):
        """Jump to the next pixelation start"""
        current_frame = self.tkvars.current_frame.get()
        try:
            new_frameno = min(
                frameno
                for frameno in self.vars.spxsf
                if frameno > current_frame
            )
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def jump_previous_px(self):
        """Jump to the previous pixelation start"""
        current_frame = self.tkvars.current_frame.get()
        try:
            new_frameno = max(
                frameno
                for frameno in self.vars.spxsf
                if frameno < current_frame
            )
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def play_flipbook(self):
        """Play current video as a flipbook"""
        raise NotImplementedError

    def pre_quit_check(
        self,
    ):
        """Checks and actions before exiting the application"""
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
                logging.info("Deleted temporary directory %s", tempdir.name)
            except AttributeError:
                pass
            #
        #
        return True

    def save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        # fill up "modified" directory with missing frames
        self.complete_modified_directory()
        original_suffix = self.vars.original_path.suffix
        selected_file = filedialog.asksaveasfilename(
            initialdir=str(self.vars.original_path.parent),
            defaultextension=original_suffix,
            parent=self.main_window,
            title="Save pixelated video as…",
        )
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
        arguments = [
            "-framerate",
            str(self.vars.frame_rate),
            "-i",
            os.path.join(
                self.vars.modified_frames.name, pixelations.FRAME_PATTERN
            ),
        ]
        if self.tkvars.export.include_audio.get():
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
        #
        if self.tkvars.crop.get():
            width = self.vars.crop_area.right - self.vars.crop_area.left
            height = self.vars.crop_area.bottom - self.vars.crop_area.top
            crop_filter = "crop=w=%s:h=%s:x=%s:y=%s," % (
                width,
                height,
                self.vars.crop_area.left,
                self.vars.crop_area.top,
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
        save_exec.add_extra_arguments("-loglevel", "error")
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
                subprocess.run((show_video_command, "--version"), check=True)
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
                check=True,
            )
        #
        return True


#
# Functions
#


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description="Pixelate an area of an image"
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
        help="An image file. If none is provided,"
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
