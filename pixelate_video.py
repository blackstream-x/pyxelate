#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

pixelate_video.py

Partially pixelate selected frames of a (short) video clip
(Tkinter-based GUI assistant)

Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the MIT License.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the LICENSE file for more details.

"""


import argparse
import logging
import mimetypes
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import tkinter

from fractions import Fraction

from tkinter import filedialog
from tkinter import messagebox

# local modules

from pyxelate import app
from pyxelate import ffmpegwrappers as ffmw
from pyxelate import gui
from pyxelate import pixelations


#
# Constants
#


SCRIPT_NAME = 'Partially pixelate a video clip'
HOMEPAGE = 'https://github.com/blackstream-x/pyxelate'
MAIN_WINDOW_TITLE = 'pyxelate: partially pixelate a video clip'

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

# Phases
OPEN_FILE = 'open_file'
START_FRAME = 'start_frame'
START_AREA = 'start_area'
END_FRAME = 'end_frame'
END_AREA = 'end_area'
PREVIEW = 'preview'
# SELECT_AREA = 'select_area'

PHASES = (
    OPEN_FILE,
    START_FRAME,
    START_AREA,
    END_FRAME,
    END_AREA,
    PREVIEW,
)

PANEL_NAMES = {
    START_FRAME: 'Select pixelation start frame',
    START_AREA: 'Select pixelation start area',
    END_FRAME: 'Select pixelation end frame',
    END_AREA: 'Select pixelation end area',
    PREVIEW: 'preview',
}

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 576

OVAL = '\u2b2d ellipse'
CIRCLE = '\u25cb circle'
RECT = '\u25ad rectangle'
SQUARE = '\u25a1 square'

SHAPES = {
    OVAL: pixelations.ELLIPSE,
    CIRCLE: pixelations.ELLIPSE,
    RECT: pixelations.RECTANGLE,
    SQUARE: pixelations.RECTANGLE,
}

ELLIPTIC_SHAPES = (OVAL, CIRCLE)
RECTANGULAR_SHAPES = (RECT, SQUARE)
QUADRATIC_SHAPES = (CIRCLE, SQUARE)
ALL_SHAPES = ELLIPTIC_SHAPES + RECTANGULAR_SHAPES

MINIMUM_TILESIZE = 10
DEFAULT_TILESIZE = 10
MAXIMUM_TILESIZE = 200
TILESIZE_INCREMENT = 5

MINIMUM_SELECTION_SIZE = 20
INITIAL_SELECTION_SIZE = 50

EMPTY_SELECTION = dict(
    frame=None,
    shape=None,
    px_shape=None,
    center_x=None,
    center_y=None,
    width=None,
    height=None)

INDICATOR_OUTLINE_WIDTH = 2

POSSIBLE_INDICATOR_COLORS = (
    'white', 'black', 'red', 'green', 'blue', 'cyan', 'yellow', 'magenta')

FRAME_PATTERN = 'frame%04d.jpg'
MAX_NB_FRAMES = 9999

ONE_MILLION = 1000000

# FIXME: Items drawn on the canvas
INDICATOR = 'indicator'
NEW_SELECTION = 'new_selection'


#
# Helper Functions
#


def get_widget_state(widget):
    """Get a widget state"""
    return widget.cget('state')


def reconfigure_widget(widget, **kwargs):
    """Reconfigure a widget, avoiding eceptions
    for nonexisting widgets
    """
    if not widget:
        return
    #
    widget.config(**kwargs)


#
# Classes
#


class Namespace(dict):

    # pylint: disable=too-many-instance-attributes

    """A dict subclass that exposes its items as attributes.

    Warning: Namespace instances only have direct access to the
    attributes defined in the visible_attributes tuple
    """

    visible_attributes = ('items', )

    def __repr__(self):
        """Object representation"""
        return '{0}({1})'.format(
            type(self).__name__,
            super().__repr__())

    def __dir__(self):
        """Members sequence"""
        return tuple(self)

    def __getattribute__(self, name):
        """Access a visible attribute
        or return an existing dict member
        """
        if name in type(self).visible_attributes:
            return object.__getattribute__(self, name)
        #
        try:
            return self[name]
        except KeyError as error:
            raise AttributeError(
                '{0!r} object has no attribute {1!r}'.format(
                    type(self).__name__, name)) from error
        #

    def __setattr__(self, name, value):
        """Set an attribute"""
        self[name] = value

    def __delattr__(self, name):
        """Delete an attribute"""
        del self[name]


class FramesCache:

    """Cache frames"""

    def __init__(self,
                 primary_dir=None,
                 secondary_dir=None,
                 limit=20,
                 file_name_pattern=FRAME_PATTERN):
        """Set paths"""
        self.primary_path = pathlib.Path(primary_dir)
        self.secondary_path = pathlib.Path(secondary_dir)
        for current_path in (self.primary_path, self.secondary_path):
            if not current_path.is_dir():
                raise ValueError('%s is not a directory!')
            #
        #
        # pylint: disable=pointless-statement ; Test for valid pattern
        file_name_pattern % 1
        # pylint: enable
        self.pattern = file_name_pattern
        self.limit = limit
        self.__cache = dict()
        self.__age = dict()

    def pop(self, frame_number):
        """Return the image for the number"""
        try:
            tk_image = self.__cache.pop(frame_number)
        except KeyError:
            return self.get_tk_image(frame_number)
        #
        self.__age.pop(frame_number, None)
        return tk_image

    def get_tk_image(self, frame_number):
        """Read the frame from disk"""
        frame_file = self.pattern % frame_number
        for base_path in (self.primary_path, self.secondary_path):
            frame_path = base_path / frame_file
            if frame_path.is_file():
                break
            #
        else:
            raise ValueError('Frame %s not found' % frame_number)
        #
        vframe = pixelations.BaseImage(
            frame_path,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        return vframe.tk_original

    def preload(self, frame_number):
        """Load a frame into the cache"""
        if frame_number not in self.__cache:
            self.__cache[frame_number] = self.get_tk_image(frame_number)
            self.__age[frame_number] = time.time()
        #
        if len(self.__cache) > self.limit:
            # TODO: delete oldest content
            logging.warning('Cache above limit!')
        #


class Actions(app.InterfacePlugin):

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
        logging.debug('Current frame# is %r', self.vars.start_at.frame)
        # self.vars.frame_file = FRAME_PATTERN % self.vars.start_at.frame
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        # Set selection (pre-configured or empty)
        self.ui_instance.adjust_selection(self.vars.end_at)
        (im_width, im_height) = self.vars.image.original.size
        sel_width = self.tkvars.selection.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width
            sel_width = max(
                INITIAL_SELECTION_SIZE,
                round(im_width / 5))
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
            height=min(sel_height, im_height))
        # set the shape
        if not self.tkvars.selection.shape.get():
            self.tkvars.selection.shape.set(OVAL)
        #
        # set tilesize
        if not self.tkvars.selection.tilesize.get():
            self.tkvars.selection.tilesize.set(DEFAULT_TILESIZE)
        #
        # set the show_preview variable by default
        self.tkvars.show_preview.set(1)

    def end_frame(self):
        """Actions before showing the end frame selection panel:
        Set frame range from the selected start frame
        to the last frame.
        Fix the selected start coordinates
        """
        self.ui_instance.adjust_frame_limits(
            minimum=self.vars.start_at.frame + 1)
        if self.vars.end_at.frame:
            self.ui_instance.adjust_current_frame(self.vars.end_at.frame)
        #
        logging.debug('Fix start coordinates:')
        self.ui_instance.store_selection(self.vars.start_at)

    def end_area(self):
        """Actions before showing the end area selection panel:
        Fix the selected frame as end frame.
        Load the frame for area selection
        """
        self.vars.end_at.frame = self.tkvars.current_frame.get()
        logging.debug('Current frame# is %r', self.vars.end_at.frame)
        self.ui_instance.adjust_selection(self.vars.end_at)
        # self.vars.frame_file = FRAME_PATTERN % self.vars.end_at.frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))

    def preview(self):
        """Actions before showing the preview panel:
        Fix the selected end coordinates
        Apply the pixelations to all images
        """
        logging.debug('Fix end coordinates:')
        self.ui_instance.store_selection(self.vars.end_at)
        #
        # Save pixelation start frame
        self.vars.opxsf.append(self.vars.start_at.frame)
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        # Set pixelations shape
        px_shape = SHAPES[self.vars.start_at.shape]
        if px_shape != SHAPES[self.vars.end_at.shape]:
            raise ValueError('Shapes at start and end must be the same!')
        #
        self.vars.modified_frames = tempfile.TemporaryDirectory()
        logging.info('Created tempdir %r', self.vars.modified_frames.name)
        pixelator = pixelations.MultiFramePixelation(
            pathlib.Path(self.vars.original_frames.name),
            pathlib.Path(self.vars.modified_frames.name),
            file_name_pattern=FRAME_PATTERN)
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Applying pixelation',
            label='Applying pixelation to selected frames …',
            maximum=100)
        for percentage in pixelator.pixelate_frames(
                self.tkvars.selection.tilesize.get(),
                px_shape,
                self.vars.start_at,
                self.vars.end_at,
                quality='maximum'):
            progress.set_current_value(percentage)
        #
        progress.action_cancel()
        self.vars.unsaved_changes = True
        self.vars.frames_cache = FramesCache(
            primary_dir=self.vars.modified_frames.name,
            secondary_dir=self.vars.original_frames.name,
            limit=20)
        self.ui_instance.adjust_frame_limits()
        self.ui_instance.adjust_current_frame(1)


class VideoCallbacks(app.Callbacks):

    """Callback functions for the video UI"""

    def change_frame(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        try:
            self.widgets.frame_canvas.delete('vframe')
        except AttributeError as error:
            logging.warning('%s', error)
        #
        current_frame = self.tkvars.current_frame.get()
        # logging.debug('Current frame# is %r', current_frame)
        if current_frame < self.vars.frame_limits.minimum:
            current_frame = self.vars.frame_limits.minimum
            logging.warning(
                'Raising current frame to minimum (%r)', current_frame)
        elif current_frame > self.vars.frame_limits.maximum:
            current_frame = self.vars.frame_limits.maximum
            logging.warning(
                'Lowering current frame to maximum (%r)', current_frame)
        #
        self.vars.trace = False
        self.tkvars.current_frame_text.set(str(current_frame))
        if current_frame != self.tkvars.current_frame.get():
            self.tkvars.current_frame.set(current_frame)
        #
        self.vars.trace = True
        if self.vars.current_panel == PREVIEW:
            self.vars.tk_image = self.vars.frames_cache.pop(current_frame)
            self.update_previewbuttons()
        else:
            self.vars.frame_file = FRAME_PATTERN % current_frame
            self.vars.vframe = pixelations.BaseImage(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
            self.vars.tk_image = self.vars.vframe.tk_original
        #
        self.widgets.frame_canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='vframe')
        #

    def change_frame_from_text(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        self.tkvars.current_frame.set(
            int(self.tkvars.current_frame_text.get()))
        #

    def update_buttons(self, *unused_arguments):
        """Trigger previous, next and save button states changes"""
        for (button_name, state_var) in self.tkvars.buttonstate.items():
            gui.set_state(self.widgets.buttons[button_name], state_var.get())
        #

    def update_previewbuttons(self):
        """Update button states if required"""
        current_frame = self.tkvars.current_frame.get()
        if any(frameno < current_frame for frameno in self.vars.spxsf):
            previous_state = tkinter.NORMAL
        else:
            previous_state = tkinter.DISABLED
        #
        if any(frameno > current_frame for frameno in self.vars.spxsf):
            next_state = tkinter.NORMAL
        else:
            next_state = tkinter.DISABLED
        #
        gui.set_state(self.widgets.previewbuttons.previous, previous_state)
        gui.set_state(self.widgets.previewbuttons.next_, next_state)


class Panels(app.Panels):

    """Panels and panel components"""

    # Components

    def component_frameselection(self, position):
        """Select the start or end frame using a slider
        abd show that frame on a canvas
        """
        # logging.debug(
        #     '%s frame# is %r', position, self.tkvars.current_frame.get())
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frames_slider.destroy()
        except AttributeError:
            pass
        #
        self.widgets.frames_slider = tkinter.Scale(
            image_frame,
            from_=self.vars.frame_limits.minimum,
            to=self.vars.frame_limits.maximum,
            length=self.ui_instance.canvas_width,
            label=f'{position} frame:',
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame)
        self.widgets.frames_slider.grid()
        self.widgets.frame_canvas = tkinter.Canvas(
            image_frame,
            width=self.ui_instance.canvas_width,
            height=self.ui_instance.canvas_height)
        self.widgets.frame_canvas.grid()
        self.vars.trace = True
        self.ui_instance.callbacks.change_frame()
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        self.sidebar_frameselection(position)
        # logging.debug(
        #     '%s frame# is %r', position, self.tkvars.current_frame.get())

    def component_image_info(self,
                             parent_frame,
                             frame_position,
                             change_enabled=False):
        """Show information about the current video frame"""
        heading = gui.Heading(
            parent_frame,
            text=f'{frame_position} frame:',
            sticky=tkinter.W,
            columnspan=4)

        # Inner function for the "extra arguments" trick, see
        # <https://tkdocs.com/shipman/extra-args.html>
        def show_help(self=self):
            return self.ui_instance.show_help('Frame')
        #
        help_button = tkinter.Button(
            parent_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
        label = tkinter.Label(
            parent_frame,
            text='Number:')
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
                state='readonly',
                width=4)
        else:
            self.widgets.frame_number = tkinter.Label(
                parent_frame,
                textvariable=self.tkvars.current_frame_text)
        #
        label.grid(sticky=tkinter.W)
        self.widgets.frame_number.grid(
            sticky=tkinter.W, columnspan=3,
            column=1, row=gui.grid_row_of(label))
        if self.vars.vframe.display_ratio > 1:
            scale_factor = 'Size: scaled down (factor: %r)' % float(
                self.vars.vframe.display_ratio)
        else:
            scale_factor = 'Size: original dimensions'
        #
        label = tkinter.Label(parent_frame, text=scale_factor)
        label.grid(sticky=tkinter.W, columnspan=4)

    def sidebar_frameselection(self, frame_position):
        """Show the settings frame"""
        frameselection_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.component_image_info(
            frameselection_frame,
            frame_position,
            change_enabled=True)
        frameselection_frame.columnconfigure(4, weight=100)
        frameselection_frame.grid(row=0, column=1, **app.GRID_FULLWIDTH)

    # Panels in order of appearance

    def start_frame(self):
        """Select the start frame using a slider
        and show that frame on a canvas
        """
        self.component_frameselection('Start')

    def start_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.component_select_area('Start')

    def end_frame(self):
        """Select the end frame using a slider
        and show that frame on a canvas
        """
        self.component_frameselection('End')

    def end_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        if self.vars.start_at.shape in ELLIPTIC_SHAPES:
            allowed_shapes = ELLIPTIC_SHAPES
        else:
            allowed_shapes = RECTANGULAR_SHAPES
        #
        self.component_select_area(
            'End',
            allowed_shapes=allowed_shapes)

    def preview(self):
        """Show a slider allowing to preview the modified video
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        buttonframe = tkinter.Frame(image_frame)
        self.widgets.previewbuttons.previous = tkinter.Button(
            buttonframe,
            text='\u23ee Previous px start',
            command=self.ui_instance.jump_previous_px)
        self.widgets.previewbuttons.next_ = tkinter.Button(
            buttonframe,
            text='\u23ef Next px start',
            command=self.ui_instance.jump_next_px)
        self.widgets.previewbuttons.play = tkinter.Button(
            buttonframe,
            text='\u23f5 Play 2 seconds',
            command=self.ui_instance.play_flipbook,
            state=tkinter.DISABLED)     # Not yet implemented
        self.ui_instance.callbacks.update_previewbuttons()
        self.widgets.previewbuttons.previous.grid(row=0, column=0)
        self.widgets.previewbuttons.next_.grid(row=0, column=1)
        self.widgets.previewbuttons.play.grid(row=0, column=2)
        buttonframe.grid(sticky=tkinter.W)
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frames_slider.destroy()
        except AttributeError:
            pass
        #
        self.widgets.frames_slider = tkinter.Scale(
            image_frame,
            from_=self.vars.frame_limits.minimum,
            to=self.vars.frame_limits.maximum,
            length=CANVAS_WIDTH,
            label='Current frame:',
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame)
        self.widgets.frames_slider.grid()
        self.widgets.frame_canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.widgets.frame_canvas.grid()
        self.vars.trace = True
        self.ui_instance.callbacks.change_frame()
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.component_file_info(sidebar_frame)
        self.component_image_info(
            sidebar_frame,
            'Current',
            change_enabled=True)
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(row=0, column=1, **app.GRID_FULLWIDTH)


class Rollbacks(app.InterfacePlugin):

    """Rollback acction in order of appearance"""

    def start_area(self):
        """Actions when clicking the "previous" button
        in the start area selection panel:
        Set frame range from the first to the last but 5th frame.
        Reset the current frame to the saved start frame
        """
        # TODO
        logging.debug(
            '%s frame# is %r', 'Start', self.tkvars.current_frame.get())
        ...

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
        self.vars.frame_file = FRAME_PATTERN % current_frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        #
        self.ui_instance.adjust_selection(self.vars.start_at)
        self.vars.trace = True

    def end_area(self):
        """Actions when clicking the "previous" button
        in the end area selection panel:
        """
        # TODO
        logging.debug(
            '%s frame# is %r', 'End', self.tkvars.current_frame.get())
        ...

    def preview(self):
        """Actions when clicking the "previous" button
        in the preview panel:
        Reset the current frame to the saved end frame
        Set the seclection to the selected end coordinates
        Cleanup the modified_frames tempdir
        """
        self.ui_instance.adjust_frame_limits(
            minimum=self.vars.start_at.frame + 1)
        self.vars.trace = False
        current_frame = self.vars.end_at.frame
        self.ui_instance.adjust_current_frame(current_frame)
        self.vars.frame_file = FRAME_PATTERN % current_frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        #
        self.ui_instance.adjust_selection(self.vars.end_at)
        self.vars.trace = True
        self.vars.opxsf.pop()
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        self.vars.modified_frames.cleanup()


class VideoUI(app.UserInterface):

    """Modular user interface for video pixelation"""

    phases = PHASES

    canvas_width = 640
    canvas_height = 480

    script_name = SCRIPT_NAME
    version = VERSION

    def __init__(self, file_path, options):
        """Initialize super class"""
        self.action_class = Actions
        self.callback_class = VideoCallbacks
        self.panel_class = Panels
        self.rollback_class = Rollbacks
        super().__init__(file_path,
                         options,
                         SCRIPT_PATH,
                         window_title=MAIN_WINDOW_TITLE)

    def additional_variables(self):
        """Subclass-specific post-initialization
        (additional variables)
        """
        super().additional_variables()
        self.vars.update(
            app.Namespace(
                original_frames=None,
                modified_frames=None,
                nb_frames=None,
                has_audio=False,
                vframe=None,
                # List of pixelation start frames
                # (original sequence, and sorted unique)
                opxsf=[],
                spxsf=[],
                frame_rate=None,
                frames_cache=None,
                duration_usec=None,
                unsaved_changes=False,
                frame_limits=app.Namespace(
                    minimum=1,
                    maximum=1),
                start_at=app.Namespace(**EMPTY_SELECTION),
                end_at=app.Namespace(**EMPTY_SELECTION)))
        self.tkvars.update(
            app.Namespace(
                current_frame=self.callbacks.get_traced_intvar(
                    'change_frame'),
                current_frame_text=self.callbacks.get_traced_stringvar(
                    'change_frame_from_text'),
                end_frame=tkinter.IntVar(),
                buttonstate=app.Namespace(
                    previous=self.callbacks.get_traced_stringvar(
                        'update_buttons', value=tkinter.DISABLED),
                    next_=self.callbacks.get_traced_stringvar(
                        'update_buttons', value=tkinter.NORMAL),
                    more=self.callbacks.get_traced_stringvar(
                        'update_buttons', value=tkinter.DISABLED))))
        #

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        self.widgets.update(
            app.Namespace(
                buttons=app.Namespace(
                    previous=None,
                    next_=None,
                    more=None),
                previewbuttons=app.Namespace(
                    previous=None,
                    next_=None,
                    play=None),
                frame_canvas=None,
                frames_slider=None,
                frame_number=None))
        #

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        file_type = mimetypes.guess_type(str(file_path))[0]
        if not file_type or not file_type.startswith('video/'):
            return False
        #
        return True

    def load_file(self, file_path):
        """Load the file. Wrap self.__load_video
        to transform a subprocess.CalledProcessError to a ValueError
        """
        try:
            self.__load_video(file_path)
        except subprocess.CalledProcessError as error:
            raise ValueError(str(error)) from error
        #

    def __load_video(self, file_path):
        """Load the video and split it into frames,
        showing a progress bar (in an auto-closing modal window?)
        """
        # Get audio and video stream information
        progress = gui.TransientWindow(
            self.main_window,
            title=f'Loading {file_path.name} (step 1)')
        label = tkinter.Label(
            progress.body,
            text='Examining audio stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining audio stream …')
        has_audio = bool(
            ffmw.get_stream_info(
                file_path,
                ffprobe_executable=self.options.ffprobe_executable,
                select_streams='a',
                show_entries=ffmw.ENTRIES_ALL))
        logging.info('%r has audio: %r', file_path.name, has_audio)
        self.vars.has_audio = has_audio
        label = tkinter.Label(
            progress.body,
            text='Examining video stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining video stream …')
        video_properties = ffmw.get_stream_info(
            file_path,
            ffprobe_executable=self.options.ffprobe_executable,
            select_streams='v')
        # Validate video properties,
        # especially nb_frames, duration and frame rates
        nb_frames = None
        frame_rate = None
        duration_usec = None
        try:
            nb_frames = int(video_properties['nb_frames'])
            frame_rate = Fraction(video_properties['avg_frame_rate'])
            duration_usec = float(
                video_properties['duration']) * ONE_MILLION
        except ValueError as error:
            logging.warning(error)
            video_data = ffmw.count_all_frames(
                file_path,
                ffmpeg_executable=self.options.ffmpeg_executable)
            nb_frames = int(video_data['frame'])
            duration_usec = int(video_data['out_time_us'])
            frame_rate = Fraction(nb_frames * ONE_MILLION, duration_usec)
        finally:
            progress.action_cancel()
        #
        if nb_frames > MAX_NB_FRAMES:
            raise ValueError(f'To many frames (maximum is {MAX_NB_FRAMES})!')
        #
        logging.debug('Duration (usec): %r', duration_usec)
        if frame_rate.denominator > 1001:
            logging.debug('Original frame rate: %s', frame_rate)
            frame_rate = frame_rate.limit_denominator(100)
        #
        logging.debug('Frame rate: %s', frame_rate)
        logging.debug('Number of frames: %s', nb_frames)
        self.vars.duration_usec = duration_usec
        self.vars.frame_rate = frame_rate
        self.vars.nb_frames = nb_frames
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Loading video',
            label=f'Splitting {file_path.name} into frames …',
            maximum=nb_frames)
        # Create a temorary directory for original frames
        self.vars.original_frames = tempfile.TemporaryDirectory()
        logging.info('Created tempdir %r', self.vars.original_frames.name)
        # Split into frames
        split_exec = ffmw.FFmpegWrapper(
            '-i', str(file_path),
            '-qscale:v', '1', '-qmin', '1',
            os.path.join(self.vars.original_frames.name, FRAME_PATTERN),
            executable=self.options.ffmpeg_executable)
        split_exec.add_extra_arguments('-loglevel', 'error')
        try:
            for line in split_exec.stream(check=True):
                if line.startswith('frame='):
                    value = line.split('=', 1)[1]
                    progress.set_current_value(int(value))
                #
            #
        finally:
            progress.action_cancel()
        #
        # Clear selection
        self.vars.start_at = app.Namespace(**EMPTY_SELECTION)
        self.vars.end_at = app.Namespace(**EMPTY_SELECTION)
        # set the original path and displayed file name
        self.vars.original_path = file_path
        self.tkvars.file_name.set(file_path.name)
        self.vars.unsaved_changes = False

    def show_additional_buttons(self, buttons_area, buttons_grid):
        """Additional buttons for the pixelate_image script"""
        self.widgets.buttons.previous = tkinter.Button(
            buttons_area,
            text='\u25c1 Previous',
            command=self.previous_panel)
        self.widgets.buttons.previous.grid(row=0, column=0, **buttons_grid)
        self.widgets.buttons.next_ = tkinter.Button(
            buttons_area,
            text='\u25b7 Next',
            command=self.next_panel)
        self.widgets.buttons.next_.grid(row=0, column=1, **buttons_grid)
        self.widgets.buttons.more = tkinter.Button(
            buttons_area,
            text='\u2795 More…',
            command=self.apply_and_recycle)
        self.widgets.buttons.more.grid(row=0, column=2, **buttons_grid)
# =============================================================================
#         try:
#             self.widgets.buttons.save = tkinter.Button(
#                 buttons_area,
#                 text='\U0001f5ab Save',
#                 command=self.save_file)
#         except tkinter.TclError:
#             self.widgets.buttons.save = tkinter.Button(
#                 buttons_area,
#                 text='\u2386 Save',
#                 command=self.save_file)
#         #
#         self.widgets.buttons.save.grid(row=0, column=2, **buttons_grid)
# =============================================================================
        # Set button states and defer state manipulations
        self.vars.trace = False
        if self.vars.current_panel == PREVIEW:
            self.tkvars.buttonstate.next_.set(tkinter.DISABLED)
            self.tkvars.buttonstate.more.set(tkinter.NORMAL)
        else:
            self.tkvars.buttonstate.more.set(tkinter.DISABLED)
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
        logging.debug(
            'Setting current frame# to %r', new_current_frame)
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
            logging.debug('Clearing selection item %r (was %r)', item, value)
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
            logging.debug('Storing selection item %r: %r', item, value)
            storage_vars[item] = value
        #
        # Respect quadratic shapes
        if storage_vars['shape'] in QUADRATIC_SHAPES:
            storage_vars['height'] = storage_vars['width']
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
            logging.debug('Setting selection item %r to %r', item, value)
            target.set(value)
        #
        self.vars.trace = previous_trace_setting

    def apply_and_recycle(self):
        """Apply changes to the frames,
        and re-cycle them as original frames
        """
        logging.debug('Applying changes and reusing the frames')
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
            frame_file = FRAME_PATTERN % frame_number
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
                frameno for frameno in self.vars.spxsf
                if frameno > current_frame)
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def jump_previous_px(self):
        """Jump to the previous pixelation start"""
        current_frame = self.tkvars.current_frame.get()
        try:
            new_frameno = max(
                frameno for frameno in self.vars.spxsf
                if frameno < current_frame)
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def play_flipbook(self):
        """Play current video as a flipbook"""
        raise NotImplementedError

    def pre_quit_check(self,):
        """Checks and actions before exiting the application"""
        if self.vars.unsaved_changes:
            if messagebox.askyesno('Unsaved Changes', 'Save your changes?'):
                if not self.save_file():
                    if not messagebox.askokcancel(
                            'Changes not saved!',
                            'Really exit without saving?',
                            default=messagebox.CANCEL):
                        return False
                    #
                #
            #
        #
        for tempdir in (self.vars.original_frames,
                        self.vars.modified_frames):
            try:
                tempdir.cleanup()
                logging.info('Deleted temporary directory %s', tempdir.name)
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
            title='Save pixelated video as…')
        if not selected_file:
            return False
        #
        logging.debug('Saving the file as %r', selected_file)
        #  save the file and reset the "touched" flag
        # self.vars.image.original.save(selected_file)
        file_path = pathlib.Path(selected_file)
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Saving video',
            label=f'Saving as {file_path.name} …',
            maximum=self.vars.nb_frames)
        # Build the video from the frames
        arguments = [
            '-framerate', str(self.vars.frame_rate),
            '-i', os.path.join(self.vars.modified_frames.name, FRAME_PATTERN)]
        if self.vars.has_audio:
            arguments.extend([
                '-i', str(self.vars.original_path),
                '-map', '0:v', '-map', '1:a',
                '-c:a', 'copy'])
        #
        arguments.extend([
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '17',
            '-vf', f'fps={self.vars.frame_rate},format=yuv420p',
            '-y', str(file_path)])
        save_exec = ffmw.FFmpegWrapper(
            *arguments,
            executable=self.options.ffmpeg_executable)
        save_exec.add_extra_arguments('-loglevel', 'error')
        try:
            for line in save_exec.stream(check=True):
                if line.startswith('frame='):
                    value = line.split('=', 1)[1]
                    progress.set_current_value(int(value))
                #
            #
        finally:
            progress.action_cancel()
        #
        self.vars.unsaved_changes = False
        return True


class UserInterface:

    """GUI using tkinter"""

    with_border = dict(
        borderwidth=2,
        padx=5,
        pady=5,
        relief=tkinter.GROOVE)
    grid_fullwidth = dict(
        padx=4,
        pady=2,
        sticky=tkinter.E + tkinter.W)

    # pylint: disable=attribute-defined-outside-init

    def __init__(self, file_path, options):
        """Build the GUI"""
        self.main_window = tkinter.Tk()
        self.main_window.title(MAIN_WINDOW_TITLE)
        self.options = options
        self.vars = Namespace(
            current_panel=None,
            errors=[],
            tk_image=None,
            image=None,
            original_path=file_path,
            trace=False,
            unsaved_changes=False,
            undo_buffer=[],
            original_frames=None,
            modified_frames=None,
            nb_frames=None,
            has_audio=False,
            vframe=None,
            # List of pixelation start frames
            # (original sequence, and sorted unique)
            opxsf=[],
            spxsf=[],
            frame_rate=None,
            duration_usec=None,
            frame_limits=Namespace(
                minimum=1,
                maximum=1),
            start_at=Namespace(**EMPTY_SELECTION),
            end_at=Namespace(**EMPTY_SELECTION),
            drag_data=Namespace(
                x=0,
                y=0,
                item=None),
        )
        self.tkvars = Namespace(
            file_name=tkinter.StringVar(),
            show_preview=tkinter.IntVar(),
            current_frame=tkinter.IntVar(),
            current_frame_text=tkinter.StringVar(),
            end_frame=tkinter.IntVar(),
            selection=Namespace(
                center_x=tkinter.IntVar(),
                center_y=tkinter.IntVar(),
                width=tkinter.IntVar(),
                height=tkinter.IntVar(),
                shape=tkinter.StringVar(),
                tilesize=tkinter.IntVar()),
            indicator=Namespace(
                color=tkinter.StringVar(),
                drag_color=tkinter.StringVar()),
            buttonstate=Namespace(
                previous=tkinter.StringVar(),
                next_=tkinter.StringVar(),
                more=tkinter.StringVar(),
                save=tkinter.StringVar()),
        )
        # Trace changes:
        # … to selection variables
        for (_, variable) in self.tkvars.selection.items():
            variable.trace_add('write', self.trigger_selection_change)
        #
        # … to the buttonstate variables
        for (_, variable) in self.tkvars.buttonstate.items():
            variable.set(tkinter.NORMAL)
            variable.trace_add('write', self.trigger_button_states)
        #
        # … to the indicator.color variable
        self.tkvars.indicator.drag_color.set('blue')
        self.tkvars.indicator.color.set('red')
        self.tkvars.indicator.color.trace_add(
            'write', self.trigger_indicator_redraw)
        #
        self.tkvars.current_frame.trace_add(
            'write', self.trigger_change_frame)
        #
        self.tkvars.current_frame_text.trace_add(
            'write', self.trigger_change_frame_from_text)
        #
        self.widgets = Namespace(
            action_area=None,
            # buttons_area=None,
            buttons=Namespace(
                previous=None,
                next_=None,
                more=None,
                save=None),
            previewbuttons=Namespace(
                previous=None,
                next_=None,
                play=None),
            frame_canvas=None,
            frames_slider=None,
            frame_number=None,
            canvas=None,
            height=None)
        self.do_choose_video(
            keep_existing=True,
            quit_on_empty_choice=True)
        self.main_window.protocol('WM_DELETE_WINDOW', self.quit)
        self.main_window.mainloop()

    def action_start_frame(self):
        """Actions before showing the start frame selection panel:
        Set frame range from the first to the last but 5th frame.
        """
        self.__do_adjust_frame_limits(maximum=self.vars.nb_frames - 5)

    def action_start_area(self):
        """Actions before showing the start area selection panel:
        Fix the selected frame as start frame.
        Load the frame and set the variables
        """
        self.vars.start_at.frame = self.tkvars.current_frame.get()
        logging.debug('Current frame# is %r', self.vars.start_at.frame)
        # self.vars.frame_file = FRAME_PATTERN % self.vars.start_at.frame
        self.vars.image = pixelations.FramePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        # Set selection (pre-configured or empty)
        self.__do_adjust_selection(self.vars.end_at)
        (im_width, im_height) = self.vars.image.original.size
        sel_width = self.tkvars.selection.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width
            sel_width = max(
                INITIAL_SELECTION_SIZE,
                round(im_width / 5))
        #
        sel_height = self.tkvars.selection.height.get()
        if not sel_height:
            sel_height = sel_width
        #
        center_x = self.tkvars.selection.center_x.get() or im_width // 2
        center_y = self.tkvars.selection.center_y.get() or im_height // 2
        self.__do_update_selection(
            center_x=center_x,
            center_y=center_y,
            width=min(sel_width, im_width),
            height=min(sel_height, im_height))
        # set the shape
        if not self.tkvars.selection.shape.get():
            self.tkvars.selection.shape.set(OVAL)
        #
        # set tilesize
        if not self.tkvars.selection.tilesize.get():
            self.tkvars.selection.tilesize.set(DEFAULT_TILESIZE)
        #
        # set the show_preview variable by default
        self.tkvars.show_preview.set(1)

    def action_end_frame(self):
        """Actions before showing the end frame selection panel:
        Set frame range from the selected start frame
        to the last frame.
        Fix the selected start coordinates
        """
        self.__do_adjust_frame_limits(minimum=self.vars.start_at.frame + 1)
        if self.vars.end_at.frame:
            self.__do_adjust_current_frame(self.vars.end_at.frame)
        #
        logging.debug('Fix start coordinates:')
        self.__do_store_selection(self.vars.start_at)

    def action_end_area(self):
        """Actions before showing the end area selection panel:
        Fix the selected frame as end frame.
        Load the frame for area selection
        """
        self.vars.end_at.frame = self.tkvars.current_frame.get()
        logging.debug('Current frame# is %r', self.vars.end_at.frame)
        self.__do_adjust_selection(self.vars.end_at)
        # self.vars.frame_file = FRAME_PATTERN % self.vars.end_at.frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))

    def action_preview(self):
        """Actions before showing the preview panel:
        Fix the selected end coordinates
        Apply the pixelations to all images
        """
        logging.debug('Fix end coordinates:')
        self.__do_store_selection(self.vars.end_at)
        #
        # Save pixelation start frame
        self.vars.opxsf.append(self.vars.start_at.frame)
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        # Set pixelations shape
        px_shape = SHAPES[self.vars.start_at.shape]
        if px_shape != SHAPES[self.vars.end_at.shape]:
            raise ValueError('Shapes at start and end must be the same!')
        #
        self.vars.modified_frames = tempfile.TemporaryDirectory()
        logging.info('Created tempdir %r', self.vars.modified_frames.name)
        pixelator = pixelations.MultiFramePixelation(
            pathlib.Path(self.vars.original_frames.name),
            pathlib.Path(self.vars.modified_frames.name),
            file_name_pattern=FRAME_PATTERN)
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Applying pixelation',
            label='Applying pixelation to selected frames …',
            maximum=100)
        for percentage in pixelator.pixelate_frames(
                self.tkvars.selection.tilesize.get(),
                px_shape,
                self.vars.start_at,
                self.vars.end_at,
                quality='maximum'):
            progress.set_current_value(percentage)
        #
        progress.action_cancel()
        self.vars.unsaved_changes = True
        self.vars.frames_cache = FramesCache(
            primary_dir=self.vars.modified_frames.name,
            secondary_dir=self.vars.original_frames.name,
            limit=20)
        self.__do_adjust_frame_limits()
        self.__do_adjust_current_frame(1)

    def cb_indicator_drag_move(self, event):
        """Handle dragging of the indicator"""
        # compute how much the mouse has moved
        current_x = event.x
        current_y = event.y
        delta_x = current_x - self.vars.drag_data.x
        delta_y = current_y - self.vars.drag_data.y
        # move the object the appropriate amount
        self.widgets.canvas.move(
            self.vars.drag_data.item, delta_x, delta_y)
        # record the new position
        self.vars.drag_data.x = current_x
        self.vars.drag_data.y = current_y
        # Update the selection (position only)
        coordinates = self.__get_bbox_selection(INDICATOR)
        self.__do_update_selection(
            center_x=coordinates.center_x,
            center_y=coordinates.center_y)
        return True

    def cb_indicator_drag_start(self, event):
        """Begining drag of the indicator"""
        # record the item and its location
        self.vars.drag_data.item = INDICATOR
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def cb_indicator_drag_stop(self, *unused_event):
        """End drag of an object"""
        # reset the drag information
        self.vars.drag_data.item = None
        self.vars.drag_data.x = 0
        self.vars.drag_data.y = 0
        # Trigger the selection change explicitly
        self.trigger_selection_change()
        return True

    def cb_selection_drag_move(self, event):
        """Drag a new selection"""
        if self.vars.drag_data.item == INDICATOR:
            return self.cb_indicator_drag_move(event)
        #
        current_x = event.x
        current_y = event.y
        [left, right] = sorted((current_x, self.vars.drag_data.x))
        [top, bottom] = sorted((current_y, self.vars.drag_data.y))
        # Respect "quadratic" shapes
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            width = right - left
            height = bottom - top
            new_size = max(width, height)
            if new_size == height:
                if current_x == left:
                    left = right - new_size
                else:
                    right = left + new_size
                #
            elif new_size == width:
                if current_y == top:
                    top = bottom - new_size
                else:
                    bottom = top + new_size
                #
            #
        #
        # Draw a new selection outline
        self.widgets.canvas.delete(NEW_SELECTION)
        outer_dash = (1, 1)
        shape = self.tkvars.selection.shape.get()
        current_color = self.tkvars.indicator.drag_color.get()
        if shape in ELLIPTIC_SHAPES:
            outer_dash = (5, 5)
        #
        self.widgets.canvas.create_rectangle(
            left, top, right, bottom,
            dash=outer_dash,
            outline=current_color,
            tags=NEW_SELECTION)
        if shape in ELLIPTIC_SHAPES:
            self.widgets.canvas.create_oval(
                left, top, right, bottom,
                dash=(1, 1),
                outline=current_color,
                tags=NEW_SELECTION)
        # Update the selection
        coordinates = self.__get_bbox_selection(NEW_SELECTION)
        self.__do_update_selection(
            center_x=coordinates.center_x,
            center_y=coordinates.center_y,
            width=coordinates.width,
            height=coordinates.height)
        return True

    def cb_selection_drag_start(self, event):
        """Begining dragging for a new selection"""
        # record the item and its location
        if self.__clicked_inside_indicator(event):
            return self.cb_indicator_drag_start(event)
        #
        self.vars.drag_data.item = NEW_SELECTION
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def cb_selection_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        if self.vars.drag_data.item == INDICATOR:
            return self.cb_indicator_drag_stop()
        #
        try:
            coordinates = self.__get_bbox_selection(NEW_SELECTION)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(NEW_SELECTION)
        # Adjust to minimum sizes
        if coordinates.width < MINIMUM_SELECTION_SIZE:
            coordinates.width = MINIMUM_SELECTION_SIZE
        #
        if coordinates.height < MINIMUM_SELECTION_SIZE:
            coordinates.height = MINIMUM_SELECTION_SIZE
        #
        # Set the selection attributes
        self.__do_update_selection(
            center_x=coordinates.center_x,
            center_y=coordinates.center_y,
            width=coordinates.width,
            height=coordinates.height)
        # Trigger the selection change explicitly
        self.trigger_selection_change()
        return True

    def __clicked_inside_indicator(self, event):
        """Return True if the click was inside the indicator"""
        try:
            (left, top, right, bottom) = self.widgets.canvas.bbox(INDICATOR)
        except TypeError as error:
            logging.debug(error)
        #
        x_position = event.x
        y_position = event.y
        if left <= x_position <= right and top <= y_position <= bottom:
            if self.tkvars.selection.shape in RECTANGULAR_SHAPES:
                return True
            #
            # Apply the standard ellipse equation
            # (see https://en.wikipedia.org/wiki/Ellipse#Standard_equation)
            # to check if the event was inside or outside the ellipse
            center_x = (left + right) / 2
            center_y = (top + bottom) / 2
            relative_x = x_position - center_x
            relative_y = y_position - center_y
            semi_x = center_x - left
            semi_y = center_y - top
            if (relative_x ** 2 / semi_x ** 2) + \
                    (relative_y ** 2 / semi_y ** 2) <= 1:
                return True
            #
        #
        return False

    def complete_modified_directory(self):
        """Fill up modified directory from souce directory"""
        original_path = pathlib.Path(self.vars.original_frames.name)
        target_path = pathlib.Path(self.vars.modified_frames.name)
        for frame_number in range(1, self.vars.nb_frames + 1):
            frame_file = FRAME_PATTERN % frame_number
            frame_target_path = target_path / frame_file
            if not frame_target_path.exists():
                frame_source_path = original_path / frame_file
                frame_source_path.rename(frame_target_path)
            #
        #

    def __do_adjust_current_frame(self, new_current_frame):
        """Adjust current frame without calling triggers"""
        previous_trace_setting = self.vars.trace
        self.vars.trace = False
        logging.debug(
            'Setting current frame# to %r', new_current_frame)
        self.tkvars.current_frame.set(new_current_frame)
        self.tkvars.current_frame_text.set(str(new_current_frame))
        self.vars.trace = previous_trace_setting

    def __do_adjust_frame_limits(self, minimum=None, maximum=None):
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

    def __do_clear_selection(self, storage_vars):
        """Clear selection in storage_vars"""
        for item in storage_vars:
            try:
                self.tkvars.selection[item]
            except KeyError:
                continue
            #
            value = storage_vars[item]
            logging.debug('Clearing selection item %r (was %r)', item, value)
            storage_vars[item] = None
        #

    def __do_store_selection(self, storage_vars):
        """Store selection in storage_vars"""
        for item in storage_vars:
            try:
                source = self.tkvars.selection[item]
            except KeyError:
                continue
            #
            value = source.get()
            logging.debug('Storing selection item %r: %r', item, value)
            storage_vars[item] = value
        #
        # Respect quadratic shapes
        if storage_vars['shape'] in QUADRATIC_SHAPES:
            storage_vars['height'] = storage_vars['width']
        #

    def __do_adjust_selection(self, new_selection_vars):
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
            logging.debug('Setting selection item %r to %r', item, value)
            target.set(value)
        #
        self.vars.trace = previous_trace_setting

    def do_apply_and_recycle(self):
        """Apply changes to the frames,
        and re-cycle them as original frames
        """
        logging.debug('Applying changes and reusing the frames')
        # fill up "modified" directory with missing frames
        self.complete_modified_directory()
        #
        self.vars.original_frames.cleanup()
        self.vars.original_frames = self.vars.modified_frames
        self.vars.modified_frames = None
        # self.vars.trace = False
        # Clear end selection
        self.__do_clear_selection(self.vars.end_at)
        #
        self.vars.current_panel = OPEN_FILE
        self.next_panel()

    def do_choose_video(self,
                        keep_existing=False,
                        preset_path=None,
                        quit_on_empty_choice=False):
        """Choose an image via file dialog"""
        self.vars.current_panel = OPEN_FILE
        file_path = self.vars.original_path
        if preset_path:
            if not preset_path.is_dir():
                initial_dir = str(preset_path.parent)
            #
        elif file_path:
            initial_dir = str(file_path.parent)
        else:
            initial_dir = os.getcwd()
        #
        while True:
            if not keep_existing or file_path is None:
                selected_file = filedialog.askopenfilename(
                    initialdir=initial_dir,
                    parent=self.main_window,
                    title='Load an image file')
                if not selected_file:
                    if quit_on_empty_choice:
                        self.quit()
                    #
                    return
                #
                file_path = pathlib.Path(selected_file)
            #
            # check for an supported file type,
            # and show an error dialog and retry
            # if the selected file is not a video
            file_type = mimetypes.guess_type(str(file_path))[0]
            if not file_type or not file_type.startswith('video/'):
                messagebox.showerror(
                    'Unsupported file type',
                    f'{file_path.name!r} is not a supported video file.',
                    icon=messagebox.ERROR)
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            if self.vars.unsaved_changes or self.vars.undo_buffer:
                confirmation = messagebox.askyesno(
                    'Unsaved Changes',
                    'Discard the chages made to'
                    f' {self.vars.original_path.name!r}?',
                    icon=messagebox.WARNING)
                if not confirmation:
                    return
                #
            #
            # Set original_path and read image data
            try:
                self.__do_load_video(file_path)
            except (OSError,
                    ValueError,
                    subprocess.CalledProcessError) as error:
                messagebox.showerror(
                    'Load error',
                    str(error),
                    icon=messagebox.ERROR)
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            break
        #
        self.vars.undo_buffer.clear()
        self.next_panel()

    def __do_draw_indicator(self, stipple=None):
        """Draw the pixelation selector on the canvas,
        its coordinates determined by the px_* variables
        """
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        width = self.vars.image.to_display_size(
            self.tkvars.selection.width.get())
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.vars.image.to_display_size(
                self.tkvars.selection.height.get())
        #
        center_x = self.vars.image.to_display_size(
            self.tkvars.selection.center_x.get())
        center_y = self.vars.image.to_display_size(
            self.tkvars.selection.center_y.get())
        left = center_x - width // 2
        right = left + width
        top = center_y - height // 2
        bottom = top + height
        shape = self.tkvars.selection.shape.get()
        canvas.delete(INDICATOR)
        if shape in ELLIPTIC_SHAPES:
            create_widget = canvas.create_oval
        elif shape in RECTANGULAR_SHAPES:
            create_widget = canvas.create_rectangle
        #
        current_color = self.tkvars.indicator.color.get()
        appearance = dict(
            width=INDICATOR_OUTLINE_WIDTH,
            outline=current_color,
            tags=INDICATOR)
        if stipple:
            appearance.update(
                dict(width=1, fill=current_color, stipple=stipple))
        #
        create_widget(
            left, top, right, bottom,
            **appearance)
        # add bindings to drag the selector over the image
        canvas.tag_bind(
            INDICATOR, "<ButtonPress-1>", self.cb_indicator_drag_start)
        canvas.tag_bind(
            INDICATOR, "<ButtonRelease-1>", self.cb_indicator_drag_stop)
        canvas.tag_bind(
            INDICATOR, "<B1-Motion>", self.cb_indicator_drag_move)

    def __do_jump_next_px(self):
        """Jump to the next pixelation start"""
        current_frame = self.tkvars.current_frame.get()
        try:
            new_frameno = min(
                frameno for frameno in self.vars.spxsf
                if frameno > current_frame)
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def __do_jump_previous_px(self):
        """Jump to the previous pixelation start"""
        current_frame = self.tkvars.current_frame.get()
        try:
            new_frameno = max(
                frameno for frameno in self.vars.spxsf
                if frameno < current_frame)
        except ValueError:
            return
        #
        self.tkvars.current_frame.set(new_frameno)

    def __do_load_video(self, file_path):
        """Load the video and split it into frames,
        showing a progress bar (in an auto-closing modal window?)
        """
        # Get audio and video stream information
        progress = gui.TransientWindow(
            self.main_window,
            title=f'Loading {file_path.name} (step 1)')
        label = tkinter.Label(
            progress.body,
            text='Examining audio stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining audio stream …')
        has_audio = bool(
            ffmw.get_stream_info(
                file_path,
                ffprobe_executable=self.options.ffprobe_executable,
                select_streams='a',
                show_entries=ffmw.ENTRIES_ALL))
        logging.info('%r has audio: %r', file_path.name, has_audio)
        self.vars.has_audio = has_audio
        label = tkinter.Label(
            progress.body,
            text='Examining video stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining video stream …')
        video_properties = ffmw.get_stream_info(
            file_path,
            ffprobe_executable=self.options.ffprobe_executable,
            select_streams='v')
        # Validate video properties,
        # especially nb_frames, duration and frame rates
        nb_frames = None
        frame_rate = None
        duration_usec = None
        try:
            nb_frames = int(video_properties['nb_frames'])
            frame_rate = Fraction(video_properties['avg_frame_rate'])
            duration_usec = float(
                video_properties['duration']) * ONE_MILLION
        except ValueError as error:
            logging.warning(error)
            video_data = ffmw.count_all_frames(
                file_path,
                ffmpeg_executable=self.options.ffmpeg_executable)
            nb_frames = int(video_data['frame'])
            duration_usec = int(video_data['out_time_us'])
            frame_rate = Fraction(nb_frames * ONE_MILLION, duration_usec)
        finally:
            progress.action_cancel()
        #
        if nb_frames > MAX_NB_FRAMES:
            raise ValueError(f'To many frames (maximum is {MAX_NB_FRAMES})!')
        #
        logging.debug('Duration (usec): %r', duration_usec)
        if frame_rate.denominator > 1001:
            logging.debug('Original frame rate: %s', frame_rate)
            frame_rate = frame_rate.limit_denominator(100)
        #
        logging.debug('Frame rate: %s', frame_rate)
        logging.debug('Number of frames: %s', nb_frames)
        self.vars.duration_usec = duration_usec
        self.vars.frame_rate = frame_rate
        self.vars.nb_frames = nb_frames
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Loading video',
            label=f'Splitting {file_path.name} into frames …',
            maximum=nb_frames)
        # Create a temorary directory for original frames
        self.vars.original_frames = tempfile.TemporaryDirectory()
        logging.info('Created tempdir %r', self.vars.original_frames.name)
        # Split into frames
        split_exec = ffmw.FFmpegWrapper(
            '-i', str(file_path),
            '-qscale:v', '1', '-qmin', '1',
            os.path.join(self.vars.original_frames.name, FRAME_PATTERN),
            executable=self.options.ffmpeg_executable)
        split_exec.add_extra_arguments('-loglevel', 'error')
        try:
            for line in split_exec.stream(check=True):
                if line.startswith('frame='):
                    value = line.split('=', 1)[1]
                    progress.set_current_value(int(value))
                #
            #
        finally:
            progress.action_cancel()
        #
        # Clear selection
        self.vars.start_at = Namespace(**EMPTY_SELECTION)
        self.vars.end_at = Namespace(**EMPTY_SELECTION)
        # set the original path and displayed file name
        self.vars.original_path = file_path
        self.tkvars.file_name.set(file_path.name)
        self.vars.unsaved_changes = False

    def __do_pixelate(self):
        """Apply the pixelation to the image and update the preview"""
        self.vars.image.set_tilesize(
            self.tkvars.selection.tilesize.get())
        width = self.tkvars.selection.width.get()
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.tkvars.selection.height.get()
        #
        self.vars.image.set_shape(
            (self.tkvars.selection.center_x.get(),
             self.tkvars.selection.center_y.get()),
            SHAPES[self.tkvars.selection.shape.get()],
            (width, height))
        self.__do_show_image()

    def __do_play_flipbook(self):
        """Play current video as a flipbook"""
        raise NotImplementedError

    def do_save_file(self):
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
            title='Save pixelated video as…')
        if not selected_file:
            return False
        #
        logging.debug('Saving the file as %r', selected_file)
        #  save the file and reset the "touched" flag
        # self.vars.image.original.save(selected_file)
        file_path = pathlib.Path(selected_file)
        progress = gui.TransientProgressDisplay(
            self.main_window,
            title='Saving video',
            label=f'Saving as {file_path.name} …',
            maximum=self.vars.nb_frames)
        # Build the video from the frames
        arguments = [
            '-framerate', str(self.vars.frame_rate),
            '-i', os.path.join(self.vars.modified_frames.name, FRAME_PATTERN)]
        if self.vars.has_audio:
            arguments.extend([
                '-i', str(self.vars.original_path),
                '-map', '0:v', '-map', '1:a',
                '-c:a', 'copy'])
        #
        arguments.extend([
            '-c:v', 'libx264',
            '-preset', 'slow',
            '-crf', '17',
            '-vf', f'fps={self.vars.frame_rate},format=yuv420p',
            '-y', str(file_path)])
        save_exec = ffmw.FFmpegWrapper(
            *arguments,
            executable=self.options.ffmpeg_executable)
        save_exec.add_extra_arguments('-loglevel', 'error')
        try:
            for line in save_exec.stream(check=True):
                if line.startswith('frame='):
                    value = line.split('=', 1)[1]
                    progress.set_current_value(int(value))
                #
            #
        finally:
            progress.action_cancel()
        #
        self.vars.unsaved_changes = False
        return True

    def __do_show_image(self):
        """Show image or preview according to the show_preview setting"""
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        canvas.delete('image')
        if self.tkvars.show_preview.get():
            self.vars.tk_image = self.vars.image.get_tk_image(
                self.vars.image.result)
        else:
            self.vars.tk_image = self.vars.image.tk_original
        #
        canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        canvas.tag_lower('image', INDICATOR)

    def __do_toggle_height(self):
        """Toggle height spinbox to follow width"""
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            reconfigure_widget(
                self.widgets.height,
                state=tkinter.DISABLED,
                textvariable=self.tkvars.selection.width)
        else:
            reconfigure_widget(
                self.widgets.height,
                state='readonly',
                textvariable=self.tkvars.selection.height)
        #

    def __do_update_button(self, button_name, new_state, collection=None):
        """Update a button state if required"""
        if collection is None:
            collection = self.widgets.buttons
        #
        button_widget = collection[button_name]
        try:
            old_state = get_widget_state(button_widget)
        except AttributeError:
            return
        #
        if old_state == new_state:
            return
        #
        reconfigure_widget(button_widget, state=new_state)
        # logging.debug(
        #    '%r button state: %r => %r', button_name, old_state, new_state)

    def __do_update_previewbuttons(self):
        """Update button states if required"""
        current_frame = self.tkvars.current_frame.get()
        if any(frameno < current_frame for frameno in self.vars.spxsf):
            previous_state = tkinter.NORMAL
        else:
            previous_state = tkinter.DISABLED
        #
        if any(frameno > current_frame for frameno in self.vars.spxsf):
            next_state = tkinter.NORMAL
        else:
            next_state = tkinter.DISABLED
        #
        collection = self.widgets.previewbuttons
        self.__do_update_button(
            'previous', previous_state, collection=collection)
        self.__do_update_button(
            'next', next_state, collection=collection)

    def __do_update_selection(self, **kwargs):
        """Update the selection for the provided key=value pairs"""
        self.vars.trace = False
        for (key, value) in kwargs.items():
            self.tkvars.selection[key].set(value)
        #
        self.vars.trace = True

    def __get_bbox_selection(self, tag_name):
        """Get the bbox selection as a Namespace with the
        selection coordinates (center and dimensions),
        calculated from display to image size
        """
        left, top, right, bottom = self.widgets.canvas.bbox(tag_name)
        center_x = self.vars.image.from_display_size((left + right) // 2)
        center_y = self.vars.image.from_display_size((top + bottom) // 2)
        width = self.vars.image.from_display_size(right - left)
        height = self.vars.image.from_display_size(bottom - top)
        return Namespace(
            center_x=center_x,
            center_y=center_y,
            width=width,
            height=height)

    def __next_action(self):
        """Execute the next action"""
        current_index = PHASES.index(self.vars.current_panel)
        next_index = current_index + 1
        try:
            next_phase = PHASES[next_index]
        except IndexError as error:
            raise ValueError(
                f'Phase number #{next_index} out of range') from error
        #
        method_display = (
            f'Action method for phase #{next_index} ({next_phase})')
        method_name = f'action_{next_phase}'
        try:
            action_method = getattr(self, method_name)
        except AttributeError:
            logging.debug('%s is undefined', method_display)
        else:
            try:
                action_method()
            except NotImplementedError as error:
                raise ValueError(
                    f'{method_display} has not been implemented yet') \
                    from error
            #
        #
        self.vars.current_phase = next_phase

    def next_panel(self):
        """Execute the next action and go to the next panel"""
        try:
            self.__next_action()
        except ValueError as error:
            self.vars.errors.append(str(error))
        #
        self.__show_panel()

    def panel_start_frame(self):
        """Select the start frame using a slider
        and show that frame on a canvas
        """
        self.__show_frameselection_panel('Start')

    def panel_start_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.vars.tk_image = self.vars.image.tk_original
        self.widgets.canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.grid()
        self.__do_draw_indicator()
        self.__do_pixelate()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.tag_bind(
            'image', "<ButtonPress-1>", self.cb_selection_drag_start)
        self.widgets.canvas.tag_bind(
            'image', "<ButtonRelease-1>", self.cb_selection_drag_stop)
        self.widgets.canvas.tag_bind(
            'image', "<B1-Motion>", self.cb_selection_drag_move)
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        self.__show_settings_frame('Start')

    def panel_end_frame(self):
        """Select the end frame using a slider
        and show that frame on a canvas
        """
        self.__show_frameselection_panel('End')

    def panel_end_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.vars.tk_image = self.vars.image.tk_original
        self.widgets.canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.grid()
        self.__do_draw_indicator()
        self.__do_pixelate()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.tag_bind(
            'image', "<ButtonPress-1>", self.cb_selection_drag_start)
        self.widgets.canvas.tag_bind(
            'image', "<ButtonRelease-1>", self.cb_selection_drag_stop)
        self.widgets.canvas.tag_bind(
            'image', "<B1-Motion>", self.cb_selection_drag_move)
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        if self.vars.start_at.shape in ELLIPTIC_SHAPES:
            allowed_shapes = ELLIPTIC_SHAPES
        else:
            allowed_shapes = RECTANGULAR_SHAPES
        #
        self.__show_settings_frame(
            'End',
            allowed_shapes=allowed_shapes)

    def panel_preview(self):
        """Show a slider allowing to preview the modified video
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        buttonframe = tkinter.Frame(image_frame)
        self.widgets.previewbuttons.previous = tkinter.Button(
            buttonframe,
            text='\u23ee Previous px start',
            command=self.__do_jump_previous_px)
        self.widgets.previewbuttons.next = tkinter.Button(
            buttonframe,
            text='\u23ef Next px start',
            command=self.__do_jump_next_px)
        self.widgets.previewbuttons.play = tkinter.Button(
            buttonframe,
            text='\u23f5 Play 2 seconds',
            command=self.__do_play_flipbook,
            state=tkinter.DISABLED)     # Not yet implemented
        self.__do_update_previewbuttons()
        self.widgets.previewbuttons.previous.grid(row=0, column=0)
        self.widgets.previewbuttons.next.grid(row=0, column=1)
        self.widgets.previewbuttons.play.grid(row=0, column=2)
        buttonframe.grid(sticky=tkinter.W)
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frames_slider.destroy()
        except AttributeError:
            pass
        #
        self.widgets.frames_slider = tkinter.Scale(
            image_frame,
            from_=self.vars.frame_limits.minimum,
            to=self.vars.frame_limits.maximum,
            length=CANVAS_WIDTH,
            label='Current frame:',
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame)
        self.widgets.frames_slider.grid()
        self.widgets.frame_canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.widgets.frame_canvas.grid()
        self.vars.trace = True
        self.trigger_change_frame()
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        sidebar_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.__show_frameinfo(
            sidebar_frame,
            'Current',
            change_enabled=True)
        sidebar_frame.columnconfigure(4, weight=100)
        sidebar_frame.grid(row=0, column=1, **app.GRID_FULLWIDTH)

    def previous_panel(self):
        """Go to the next panel"""
        phase_name = self.vars.current_panel
        phase_index = PHASES.index(phase_name)
        method_display = (
            f'Rollback method for phase #{phase_index} ({phase_name})')
        method_name = f'rollback_{phase_name}'
        try:
            rollback_method = getattr(self, method_name)
        except AttributeError:
            logging.warning('%s is undefined', method_display)
        else:
            self.vars.current_phase = PHASES[phase_index - 1]
            try:
                rollback_method()
            except NotImplementedError:
                self.vars.errors.append(
                    f'{method_display} has not been implemented yet')
            #
        #
        self.__show_panel()

    def quit(self, event=None):
        """Exit the application"""
        del event
        #
        if self.vars.unsaved_changes:
            if messagebox.askyesno('Unsaved Changes', 'Save your changes?'):
                if not self.do_save_file():
                    if not messagebox.askokcancel(
                            'Changes not saved!',
                            'Really exit without saving?',
                            default=messagebox.CANCEL):
                        return
                    #
                #
            #
        #
        for tempdir in (self.vars.original_frames,
                        self.vars.modified_frames):
            try:
                tempdir.cleanup()
                logging.info('Deleted temporary directory %s', tempdir.name)
            except AttributeError:
                pass
            #
        #
        self.main_window.destroy()

    def rollback_start_area(self):
        """Actions when clicking the "previous" button
        in the start area selection panel:
        Set frame range from the first to the last but 5th frame.
        Reset the current frame to the saved start frame
        """
        # TODO
        logging.debug(
            '%s frame# is %r', 'Start', self.tkvars.current_frame.get())
        ...

    def rollback_end_frame(self):
        """Actions when clicking the "previous" button
        in the end_frame selection panel:
        Set frame range from the first to the last but 5th frame.
        Reset the current frame to the saved start frame
        """
        self.__do_adjust_frame_limits(maximum=self.vars.nb_frames - 5)
        self.vars.trace = False
        current_frame = self.vars.start_at.frame
        self.__do_adjust_current_frame(current_frame)
        self.vars.frame_file = FRAME_PATTERN % current_frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        #
        self.__do_adjust_selection(self.vars.start_at)
        self.vars.trace = True

    def rollback_end_area(self):
        """Actions when clicking the "previous" button
        in the end area selection panel:
        """
        # TODO
        logging.debug(
            '%s frame# is %r', 'End', self.tkvars.current_frame.get())
        ...

    def rollback_preview(self):
        """Actions when clicking the "previous" button
        in the preview panel:
        Reset the current frame to the saved end frame
        Set the seclection to the selected end coordinates
        Cleanup the modified_frames tempdir
        """
        self.__do_adjust_frame_limits(minimum=self.vars.start_at.frame + 1)
        self.vars.trace = False
        current_frame = self.vars.end_at.frame
        self.__do_adjust_current_frame(current_frame)
        self.vars.frame_file = FRAME_PATTERN % current_frame
        self.vars.image = pixelations.ImagePixelation(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        #
        self.__do_adjust_selection(self.vars.end_at)
        self.vars.trace = True
        self.vars.opxsf.pop()
        self.vars.spxsf = sorted(set(self.vars.opxsf))
        self.vars.modified_frames.cleanup()

    def show_about(self):
        """Show information about the application
        in a modal dialog
        """
        gui.InfoDialog(
            self.main_window,
            (SCRIPT_NAME,
             'Version: {0}\nProject homepage: {1}'.format(
                VERSION, HOMEPAGE)),
            ('Copyright/License:', COPYRIGHT_NOTICE),
            title='About…')
        #

    def __show_errors(self):
        """Show errors if there are any"""
        if self.vars.errors:
            gui.InfoDialog(
                self.main_window,
                ('Errors:', '\n'.join(self.vars.errors)),
                title='Errors occurred!')
            self.vars.errors.clear()
        #

    def __show_help(self, topic='Global'):
        """Show help for the provided topic"""
        info_sequence = [('Error:', f'No help for {topic} available yet')]
        #
        gui.InfoDialog(
            self.main_window,
            *info_sequence,
            title=f'Help ({topic})')

    def __show_panel(self):
        """Show a panel.
        Add the "Previous", "Next", "Choose another relase",
        "About" and "Quit" buttons at the bottom
        """
        try:
            self.widgets.action_area.grid_forget()
        except AttributeError:
            pass
        #
        self.widgets.action_area = tkinter.Frame(self.main_window)
        try:
            panel_method = getattr(
                self,
                'panel_%s' % self.vars.current_phase)
        except AttributeError:
            self.vars.errors.append(
                'Panel for Phase %r has not been implemented yet,'
                ' going back to phase %r.' % (
                    self.vars.current_phase,
                    self.vars.current_panel))
            self.vars.current_phase = self.vars.current_panel
            panel_method = getattr(
                self,
                'panel_%s' % self.vars.current_phase)
        else:
            self.vars.current_panel = self.vars.current_phase
        #
        self.__show_errors()
        panel_method()
        self.widgets.action_area.grid(**app.GRID_FULLWIDTH)
        #
        # Set button states depending on the panel
        if self.vars.current_panel == PREVIEW:
            self.tkvars.buttonstate.previous.set(tkinter.NORMAL)
            self.tkvars.buttonstate.next_.set(tkinter.DISABLED)
            self.tkvars.buttonstate.more.set(tkinter.NORMAL)
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
        else:
            if self.vars.current_panel == START_FRAME:
                self.tkvars.buttonstate.previous.set(tkinter.DISABLED)
            else:
                self.tkvars.buttonstate.previous.set(tkinter.NORMAL)
            #
            self.tkvars.buttonstate.next_.set(tkinter.NORMAL)
            self.tkvars.buttonstate.more.set(tkinter.DISABLED)
            self.tkvars.buttonstate.save.set(tkinter.DISABLED)
        #
        buttons_area = tkinter.Frame(self.widgets.action_area)
        buttons_grid = dict(padx=5, pady=5, sticky=tkinter.E)
        self.widgets.buttons.previous = tkinter.Button(
            buttons_area,
            text='\u25c1 Previous',
            command=self.previous_panel)
        self.widgets.buttons.previous.grid(row=0, column=0, **buttons_grid)
        self.widgets.buttons.next_ = tkinter.Button(
            buttons_area,
            text='\u25b7 Next',
            command=self.next_panel)
        self.widgets.buttons.next_.grid(row=0, column=1, **buttons_grid)
        try:
            self.widgets.buttons.save = tkinter.Button(
                buttons_area,
                text='\U0001f5ab Save',
                command=self.do_save_file)
        except tkinter.TclError:
            self.widgets.buttons.save = tkinter.Button(
                buttons_area,
                text='\u2386 Save',
                command=self.do_save_file)
        #
        self.widgets.buttons.save.grid(row=0, column=2, **buttons_grid)
        self.widgets.buttons.more = tkinter.Button(
            buttons_area,
            text='\u2795 More…',
            command=self.do_apply_and_recycle)
        self.widgets.buttons.more.grid(row=1, column=0, **buttons_grid)
        self.trigger_button_states()
        about_button = tkinter.Button(
            buttons_area,
            text='\u24d8 About',
            command=self.show_about)
        about_button.grid(row=1, column=1, **buttons_grid)
        quit_button = tkinter.Button(
            buttons_area,
            text='\u23fb Quit',
            command=self.quit)
        quit_button.grid(row=1, column=2, **buttons_grid)
        self.widgets.action_area.rowconfigure(1, weight=100)
        buttons_area.grid(row=2, column=1, sticky=tkinter.E)

    def __show_shape_settings(self,
                              settings_frame,
                              fixed_tilesize=False,
                              allowed_shapes=ALL_SHAPES):
        """Show the shape part of the settings frame"""
        heading = gui.Heading(
            settings_frame,
            text='Selection:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.__show_help('Selection')
        #
        help_button = tkinter.Button(
            settings_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
        label = tkinter.Label(
            settings_frame,
            text='Tile size:')
        if fixed_tilesize:
            ts_state = tkinter.DISABLED
        else:
            ts_state = 'readonly'
        #
        tilesize = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_TILESIZE,
            to=MAXIMUM_TILESIZE,
            increment=TILESIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state=ts_state,
            width=4,
            textvariable=self.tkvars.selection.tilesize)
        #
        label.grid(sticky=tkinter.W, column=0)
        tilesize.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        label = tkinter.Label(
            settings_frame,
            text='Shape:')
        shape_opts = tkinter.OptionMenu(
            settings_frame,
            self.tkvars.selection.shape,
            *allowed_shapes)
        label.grid(sticky=tkinter.W, column=0)
        shape_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        label = tkinter.Label(
            settings_frame,
            text='Width:')
        width = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.width,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.tkvars.selection.width)
        label.grid(sticky=tkinter.W, column=0)
        width.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        label = tkinter.Label(
            settings_frame,
            text='Height:')
        self.widgets.height = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.height,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.tkvars.selection.height)
        label.grid(sticky=tkinter.W, column=0)
        self.widgets.height.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        label = tkinter.Label(
            settings_frame,
            text='Center at x:')
        center_x = tkinter.Spinbox(
            settings_frame,
            from_=0,
            to=self.vars.image.original.width,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_x)
        label_sep = tkinter.Label(
            settings_frame,
            text=', y:')
        center_y = tkinter.Spinbox(
            settings_frame,
            from_=0,
            to=self.vars.image.original.height,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_y)
        label.grid(sticky=tkinter.W, column=0)
        center_x.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1)
        label_sep.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=2)
        center_y.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=3)
        label = tkinter.Label(
            settings_frame,
            text='Preview:')
        preview_active = tkinter.Checkbutton(
            settings_frame,
            command=self.__do_show_image,
            text='active',
            variable=self.tkvars.show_preview,
            indicatoron=1)
        label.grid(sticky=tkinter.W, column=0)
        preview_active.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)

    def __show_frameinfo(self,
                         parent_frame,
                         frame_position,
                         change_enabled=False):
        """Show information about the current video frame"""
        heading = gui.Heading(
            parent_frame,
            text='Original file:',
            sticky=tkinter.W,
            columnspan=4)
        label = tkinter.Label(
            parent_frame,
            textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            parent_frame,
            text='Choose another file',
            command=self.do_choose_video)
        choose_button.grid(sticky=tkinter.W, columnspan=4)
        heading = gui.Heading(
            parent_frame,
            text=f'{frame_position} frame:',
            sticky=tkinter.W,
            columnspan=4)
        label = tkinter.Label(
            parent_frame,
            text='Number:')
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
                state='readonly',
                width=4)
        else:
            self.widgets.frame_number = tkinter.Label(
                parent_frame,
                textvariable=self.tkvars.current_frame_text)
        #
        label.grid(sticky=tkinter.W)
        self.widgets.frame_number.grid(
            sticky=tkinter.W, columnspan=3,
            column=1, row=gui.grid_row_of(label))
        if self.vars.vframe.display_ratio > 1:
            scale_factor = 'Size: scaled down (factor: %r)' % float(
                self.vars.vframe.display_ratio)
        else:
            scale_factor = 'Size: original dimensions'
        #
        label = tkinter.Label(parent_frame, text=scale_factor)
        label.grid(sticky=tkinter.W, columnspan=4)

    def __show_frameselection_sidebar(self, frame_position):
        """Show the settings frame"""
        frameselection_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.__show_frameinfo(
            frameselection_frame,
            frame_position,
            change_enabled=True)
        frameselection_frame.columnconfigure(4, weight=100)
        frameselection_frame.grid(row=0, column=1, **app.GRID_FULLWIDTH)

    def __show_frameselection_panel(self, position):
        """Select the start or end frame using a slider
        abd show that frame on a canvas
        """
        logging.debug(
            '%s frame# is %r', position, self.tkvars.current_frame.get())
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        # Destroy a pre-existing widget to remove variable limits set before
        try:
            self.widgets.frames_slider.destroy()
        except AttributeError:
            pass
        #
        self.widgets.frames_slider = tkinter.Scale(
            image_frame,
            from_=self.vars.frame_limits.minimum,
            to=self.vars.frame_limits.maximum,
            length=CANVAS_WIDTH,
            label=f'{position} frame:',
            orient=tkinter.HORIZONTAL,
            variable=self.tkvars.current_frame)
        self.widgets.frames_slider.grid()
        self.widgets.frame_canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.widgets.frame_canvas.grid()
        self.vars.trace = True
        self.trigger_change_frame()
        image_frame.grid(row=0, column=0, rowspan=3, **app.GRID_FULLWIDTH)
        self.__show_frameselection_sidebar(position)
        logging.debug(
            '%s frame# is %r', position, self.tkvars.current_frame.get())

    def __show_settings_frame(self,
                              frame_position,
                              fixed_tilesize=False,
                              allowed_shapes=ALL_SHAPES):
        """Show the settings frame"""
        settings_frame = tkinter.Frame(
            self.widgets.action_area,
            **app.WITH_BORDER)
        self.__show_frameinfo(
            settings_frame, frame_position, change_enabled=False)
        self.__show_shape_settings(
            settings_frame,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes)
        heading = gui.Heading(
            settings_frame,
            text='Indicator colours:',
            sticky=tkinter.W,
            columnspan=4)
        label = tkinter.Label(
            settings_frame,
            text='Current:')
        color_opts = tkinter.OptionMenu(
            settings_frame,
            self.tkvars.indicator.color,
            *POSSIBLE_INDICATOR_COLORS)
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        label = tkinter.Label(
            settings_frame,
            text='New:')
        color_opts = tkinter.OptionMenu(
            settings_frame,
            self.tkvars.indicator.drag_color,
            *POSSIBLE_INDICATOR_COLORS)
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)
        settings_frame.columnconfigure(4, weight=100)
        settings_frame.grid(row=0, column=1, **app.GRID_FULLWIDTH)
        self.__do_toggle_height()

    def trigger_button_states(self, *unused_arguments):
        """Trigger undo, apply and save button states changes"""
        for (button_name, state_var) in self.tkvars.buttonstate.items():
            self.__do_update_button(
                button_name, state_var.get(),
                collection=self.widgets.buttons)
        #

    def trigger_change_frame(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        try:
            self.widgets.frame_canvas.delete('vframe')
        except AttributeError as error:
            logging.warning('%s', error)
        #
        current_frame = self.tkvars.current_frame.get()
        # logging.debug('Current frame# is %r', current_frame)
        if current_frame < self.vars.frame_limits.minimum:
            current_frame = self.vars.frame_limits.minimum
            logging.warning(
                'Raising current frame to minimum (%r)', current_frame)
        elif current_frame > self.vars.frame_limits.maximum:
            current_frame = self.vars.frame_limits.maximum
            logging.warning(
                'Lowering current frame to maximum (%r)', current_frame)
        #
        self.vars.trace = False
        self.tkvars.current_frame_text.set(str(current_frame))
        if current_frame != self.tkvars.current_frame.get():
            self.tkvars.current_frame.set(current_frame)
        #
        self.vars.trace = True
        if self.vars.current_panel == PREVIEW:
            self.vars.tk_image = self.vars.frames_cache.pop(current_frame)
            self.__do_update_previewbuttons()
        else:
            self.vars.frame_file = FRAME_PATTERN % current_frame
            self.vars.vframe = pixelations.BaseImage(
                pathlib.Path(self.vars.original_frames.name)
                / self.vars.frame_file,
                canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
            self.vars.tk_image = self.vars.vframe.tk_original
        #
        self.widgets.frame_canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='vframe')
        #

    def trigger_change_frame_from_text(self, *unused_arguments):
        """Trigger a change of the frame"""
        if not self.vars.trace:
            return
        #
        self.tkvars.current_frame.set(
            int(self.tkvars.current_frame_text.get()))
        #

    def trigger_indicator_redraw(self, *unused_arguments):
        """Trigger redrawing of the indicator"""
        try:
            self.__do_draw_indicator()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def trigger_preview_toggle(self, *unused_arguments):
        """Trigger preview update"""
        try:
            self.__do_show_image()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def trigger_selection_change(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.__do_pixelate()
            self.__do_draw_indicator()
        #
        self.__do_toggle_height()


#
# Functions
#


def __get_arguments():
    """Parse command line arguments"""
    argument_parser = argparse.ArgumentParser(
        description='Pixelate an area of an image')
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
        '--ffmpeg-executable',
        default=ffmw.FFMPEG,
        help='ffmpeg executable (default: %(default)s)')
    argument_parser.add_argument(
        '--ffprobe-executable',
        default=ffmw.FFPROBE,
        help='ffprobe executable (default: %(default)s)')
    argument_parser.add_argument(
        'image_file',
        nargs='?',
        type=pathlib.Path,
        help='An image file. If none is provided,'
        ' the script will ask for a file.')
    return argument_parser.parse_args()


def main(arguments):
    """Main script function"""
    logging.basicConfig(
        format='%(levelname)-8s\u2551 %(funcName)s → %(message)s',
        level=arguments.loglevel)
    selected_file = arguments.image_file
    if selected_file and not selected_file.is_file():
        selected_file = None
    #
    VideoUI(selected_file, arguments)


if __name__ == '__main__':
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
