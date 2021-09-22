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
import time
import tkinter

from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk

# local modules

from pyxelate import ffmpegwrappers as ffmw
from pyxelate import gui_commons
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
CHOOSE_VIDEO = 'choose_video'
START_FRAME = 'start_frame'
START_AREA = 'start_area'
END_FRAME = 'end_frame'
END_AREA = 'end_area'
PREVIEW = 'preview'
# SELECT_AREA = 'select_area'

PHASES = (
    CHOOSE_VIDEO,
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

ELLIPSE = 'ellipse'
RECTANGLE = 'rectangle'

OVAL = '\u2b2d ellipse'
CIRCLE = '\u25cb circle'
RECT = '\u25ad rectangle'
SQUARE = '\u25a1 square'

SHAPES = {
    OVAL: ELLIPSE,
    CIRCLE: ELLIPSE,
    RECT: RECTANGLE,
    SQUARE: RECTANGLE,
}

ELLIPTIC_SHAPES = (OVAL, CIRCLE)
RECTANGULAR_SHAPES = (RECT, SQUARE)
QUADRATIC_SHAPES = (CIRCLE, SQUARE)
ALL_SHAPES = ELLIPTIC_SHAPES + RECTANGULAR_SHAPES

MINIMUM_TILESIZE = 10
MAXIMUM_TILESIZE = 200
TILESIZE_INCREMENT = 5

MINIMUM_SELECTION_SIZE = 20
INITIAL_SELECTION_SIZE = 50

INDICATOR_OUTLINE_WIDTH = 9

POSSIBLE_INDICATOR_COLORS = (
    'white', 'black', 'red', 'green', 'blue', 'cyan', 'yellow', 'magenta')

UNDO_SIZE = 20

HEADINGS_FONT = (None, 10, 'bold')

FRAME_PATTERN = 'frame%04d.jpg'
MAX_NB_FRAMES = 9999


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


def show_heading(frame, text, **kwargs):
    """Show a heading in the headings font,
    grid-positioned using **kwargs
    """
    heading = tkinter.Label(frame, font=HEADINGS_FONT, text=text)
    heading.grid(**kwargs)


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


class FrozenSelection:

    """Store a selection state"""

    variables = ('center_x', 'center_y', 'width', 'height',
                 'shape', 'tilesize')

    def __init__(self, selection):
        """Initialize values from the variables in the
        provided selection Namespace of tkinter variables
        """
        self.original_values = {key: selection[key].get()
                                for key in self.variables}
        self.effective_values = dict(self.original_values)
        if self.effective_values['shape'] in QUADRATIC_SHAPES:
            self.effective_values['height'] = self.effective_values['width']
        #

    def restore_to(self, px_image):
        """Restore values to the variables in the
        provided px_image Namespace of tkinter variables
        """
        for (key, value) in self.original_values.items():
            px_image[key].set(value)
        #

    def __eq__(self, other):
        """Return True if the effective values are equal"""
        for (key, value) in self.effective_values.items():
            if value != other.effective_values[key]:
                return False
            #
        #
        return True

    def __str__(self,):
        """Effective selection representation"""
        return repr(tuple(self.effective_values.values()))


class GenericProgress(gui_commons.TransientWindow):

    """Show one progressbar in a transient modal window"""

    def __init__(self,
                 parent,
                 label=None,
                 maximum=None,
                 title=None):
        """Create the toplevel window"""
        self.maximum = maximum
        super().__init__(parent, content=label, title=title)

    def create_content(self, content):
        """Create a progressbar"""
        self.widgets['current_value'] = tkinter.IntVar()
        label = tkinter.Label(
            self.body,
            text=content)
        progressbar = ttk.Progressbar(
            self.body,
            length=300,
            variable=self.widgets['current_value'],
            maximum=self.maximum,
            orient=tkinter.HORIZONTAL)
        label.grid(sticky=tkinter.W)
        progressbar.grid()
        self.widgets['progress'] = progressbar

    def set_current_value(self, current_value):
        """Set the current value"""
        self.widgets['current_value'].set(current_value)
        self.widgets['progress'].update()
        self.update_idletasks()


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

    def __init__(self, file_path):
        """Build the GUI"""
        self.main_window = tkinter.Tk()
        self.main_window.title(MAIN_WINDOW_TITLE)
        self.vars = Namespace(
            original_frames=None,
            modified_frames=None,
            nb_frames=None,
            framerate=None,
            current_panel=None,
            errors=[],
            tk_image=None,
            image=None,
            vframe=None,
            original_path=file_path,
            trace=False,
            unapplied_changes=False,
            undo_buffer=[],
            frame_limits=Namespace(
                minimum=1,
                maximum=1),
            start_at=Namespace(
                frame=None,
                shape=None,
                center_x=None,
                center_y=None,
                width=None,
                height=None),
            end_at=Namespace(
                frame=None,
                shape=None,
                center_x=None,
                center_y=None,
                width=None,
                height=None),
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
                apply=tkinter.StringVar(),
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
                apply=None,
                save=None),
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
        """Actions before showing the start frame:
        Set frame range from the firstto the last but 5th frame
        """
        self.vars.frame_limits.minimum = 1
        self.vars.frame_limits.maximum = self.vars.nb_frames - 5

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
        coordinates = self.__get_bbox_selection('indicator')
        self.__do_update_selection(
            center_x=coordinates.center_x,
            center_y=coordinates.center_y)

    def cb_indicator_drag_start(self, event):
        """Begining drag of the indicator"""
        # record the item and its location
        self.vars.drag_data.item = 'indicator'
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y

    def cb_indicator_drag_stop(self, *unused_event):
        """End drag of an object"""
        # reset the drag information
        self.vars.drag_data.item = None
        self.vars.drag_data.x = 0
        self.vars.drag_data.y = 0
        # Trigger the selection change explicitly
        self.trigger_selection_change()

    def cb_selection_drag_move(self, event):
        """Drag a new selection"""
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
        self.widgets.canvas.delete('size')
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
            tags='size')
        if shape in ELLIPTIC_SHAPES:
            self.widgets.canvas.create_oval(
                left, top, right, bottom,
                dash=(1, 1),
                outline=current_color,
                tags='size')
        # Update the selection
        coordinates = self.__get_bbox_selection('size')
        self.__do_update_selection(
            center_x=coordinates.center_x,
            center_y=coordinates.center_y,
            width=coordinates.width,
            height=coordinates.height)

    def cb_selection_drag_start(self, event):
        """Begining dragging for a new selection"""
        # record the item and its location
        self.vars.drag_data.item = 'size'
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y

    def cb_selection_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        try:
            coordinates = self.__get_bbox_selection('size')
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return
        #
        self.widgets.canvas.delete('size')
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

    def do_apply_changes(self):
        """Apply changes to the image"""
        # Append the current state to the undo buffer
        self.vars.undo_buffer.append(
            (self.vars.image.original,
             FrozenSelection(self.tkvars.selection),
             self.vars.unapplied_changes))
        if len(self.vars.undo_buffer) > UNDO_SIZE:
            del self.vars.undo_buffer[:-UNDO_SIZE]
        #
        # Visual feedback
        self.__do_draw_indicator(stipple='gray75')
        self.main_window.update_idletasks()
        time.sleep(.2)
        self.__do_draw_indicator()
        self.vars.image.set_original(self.vars.image.result)
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.NORMAL)
        self.trigger_preview_toggle()
        self.vars.unapplied_changes = False

    def do_choose_video(self,
                        keep_existing=False,
                        preset_path=None,
                        quit_on_empty_choice=False):
        """Choose an image via file dialog"""
        self.vars.current_panel = CHOOSE_VIDEO
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
            if self.vars.unapplied_changes or self.vars.undo_buffer:
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
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.DISABLED)
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
        canvas.delete('indicator')
        if shape in ELLIPTIC_SHAPES:
            create_widget = canvas.create_oval
        elif shape in RECTANGULAR_SHAPES:
            create_widget = canvas.create_rectangle
        #
        current_color = self.tkvars.indicator.color.get()
        appearance = dict(
            width=INDICATOR_OUTLINE_WIDTH,
            outline=current_color,
            tags='indicator')
        if stipple:
            appearance.update(
                dict(width=1, fill=current_color, stipple=stipple))
        #
        create_widget(
            left, top, right, bottom,
            **appearance)
        # add bindings to drag the selector over the image
        canvas.tag_bind(
            'indicator', "<ButtonPress-1>", self.cb_indicator_drag_start)
        canvas.tag_bind(
            'indicator', "<ButtonRelease-1>", self.cb_indicator_drag_stop)
        canvas.tag_bind(
            'indicator', "<B1-Motion>", self.cb_indicator_drag_move)

    def __do_load_video(self, file_path):
        """Load the video and split it into frames,
        showing a progress bar (in an auto-closing modal window?)
        """
        # Get audio and video stream information
        progress = gui_commons.TransientWindow(
            self.main_window,
            title=f'Loading {file_path.name} (step 1)')
        label = tkinter.Label(
            progress.body,
            text='Examining audio stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining audio stream …')
        has_audio = bool(
            ffmw.get_stream_info(file_path,
                                 select_streams='a',
                                 show_entries=ffmw.ENTRIES_ALL))
        logging.info('%r has audio: %r', file_path.name, has_audio)
        label = tkinter.Label(
            progress.body,
            text='Examining video stream …')
        label.grid()
        progress.update_idletasks()
        logging.debug('Examining video stream …')
        video_properties = ffmw.get_stream_info(
            file_path, select_streams='v')
        progress.action_cancel()
        # TODO: validate video properties,
        # especially nb_frames, duration and frame rates
        nb_frames = int(video_properties['nb_frames'])
        if nb_frames > MAX_NB_FRAMES:
            progress.action_cancel()
            raise ValueError(f'To many frames (maximum is {MAX_NB_FRAMES})!')
        #
        progress = GenericProgress(
            self.main_window,
            title='Loading video',
            label=f'Splitting {file_path.name} into frames …',
            maximum=nb_frames)
        # Create temorary directory for original frames
        self.vars.nb_frames = nb_frames
        self.vars.original_frames = tempfile.TemporaryDirectory()
        logging.info('Created tempdir %r', self.vars.original_frames.name)
        # Split into frames
        kwargs = dict(
            stderr=ffmw.AsynchronousLineReader,
            stdout=ffmw.AsynchronousLineReader)
        if sys.platform != 'win32':
            kwargs['close_fds'] = True
        #
        collected_stdout = []
        collected_stderr = []
        process_info = ffmw.get_streams_and_process(
            (
                'ffmpeg', '-v', 'error', '-progress', '-',
                '-i', str(file_path),
                os.path.join(self.vars.original_frames.name, FRAME_PATTERN)),
            **kwargs)
        process = process_info['process']
        stdout_reader = process_info['stdout']
        stderr_reader = process_info['stderr']
        while not stdout_reader.eof() or not stderr_reader.eof():
            # Show what has been received from stderr and stdout,
            # then sleep a short time before polling again
            for line in stderr_reader.readlines():
                line = line.decode().rstrip()
                collected_stderr.append(line)
                logging.error(line)
            #
            for line in stdout_reader.readlines():
                line = line.decode().rstrip()
                collected_stdout.append(line)
                if line.startswith('frame='):
                    value = line.split('=', 1)[1]
                    progress.set_current_value(int(value))
                #
            time.sleep(.1)
        # Cleanup:
        # Wait for the threads to end and close the file descriptors
        stderr_reader.join()
        stdout_reader.join()
        process.stderr.close()
        process.stdout.close()
        progress.action_cancel()
        completed_process = subprocess.CompletedProcess(
            args=process.args,
            returncode=process.wait(),
            stdout='\n'.join(collected_stdout),
            stderr='\n'.join(collected_stderr))
        completed_process.check_returncode()
        # set the original path and displayed file name
        self.vars.original_path = file_path
        self.tkvars.file_name.set(file_path.name)
        self.vars.unapplied_changes = False

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

    def do_save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        if not self.__get_save_recommendation(ask_to_apply=True):
            messagebox.showinfo(
                'Image unchanged', 'Nothing to save.')
            return False
        #
        original_suffix = self.vars.original_path.suffix
        filetypes = [('Supported image files', f'*{suffix}') for suffix
                     in self.vars.save_support] + [('All files', '*.*')]
        selected_file = filedialog.asksaveasfilename(
            initialdir=str(self.vars.original_path.parent),
            defaultextension=original_suffix,
            filetypes=filetypes,
            parent=self.main_window,
            title='Save pixelated image as…')
        if not selected_file:
            return False
        #
        logging.debug('Saving the file as %r', selected_file)
        #  save the file and reset the "touched" flag
        self.vars.image.original.save(selected_file)
        self.vars.original_path = pathlib.Path(selected_file)
        self.tkvars.file_name.set(self.vars.original_path.name)
        self.vars.undo_buffer.clear()
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.DISABLED)
        self.vars.unapplied_changes = False
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
        canvas.tag_lower('image', 'indicator')

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

    def do_undo(self):
        """Revert to the state before doing the last apply"""
        try:
            last_state = self.vars.undo_buffer.pop()
        except IndexError:
            return
        #
        if not self.vars.undo_buffer:
            self.__do_update_button('undo', tkinter.DISABLED)
        #
        (previous_image, previous_selection, unapplied_changes) = last_state
        self.vars.image.set_original(previous_image)
        self.vars.trace = False
        previous_selection.restore_to(self.tkvars.selection)
        self.vars.trace = True
        self.__do_pixelate()
        self.__do_draw_indicator(stipple='error')
        self.main_window.update_idletasks()
        time.sleep(.2)
        self.__do_draw_indicator()
        self.vars.unapplied_changes = unapplied_changes
        self.tkvars.buttonstate.apply.set(tkinter.NORMAL)

    def __do_update_button(self, button_name, new_state):
        """Update a button state if required"""
        button_widget = self.widgets.buttons[button_name]
        try:
            old_state = get_widget_state(button_widget)
        except AttributeError:
            return
        #
        if old_state == new_state:
            return
        #
        reconfigure_widget(button_widget, state=new_state)
        logging.debug(
            '%r button state: %r => %r', button_name, old_state, new_state)

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

    def __get_save_recommendation(self, ask_to_apply=False):
        """Return True or False (depending on the necessity to
        save the image)
        """
        try:
            last_applied_selection = self.vars.undo_buffer[-1][1]
        except IndexError:
            logging.debug('No last applied selection!')
        else:
            current_selection = FrozenSelection(self.tkvars.selection)
            logging.debug('Last applied selection: %s', last_applied_selection)
            logging.debug('Current selection:      %s', current_selection)
            logging.debug(
                'Selections are equal: %r',
                current_selection == last_applied_selection)
        #
        if self.vars.unapplied_changes:
            if not ask_to_apply:
                return True
            #
            if self.tkvars.show_preview.get():
                default_answer = messagebox.YES
            else:
                default_answer = messagebox.NO
            #
            if messagebox.askyesno(
                    'Not yet applied changes',
                    'Pixelate the current selection before saving?',
                    default=default_answer):
                self.do_apply_changes()
            #
        #
        return bool(self.vars.undo_buffer)

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
        abd show that frame on a canvas
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
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
            label='Start frame:',
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
        image_frame.grid(row=0, column=0, rowspan=3, **self.grid_fullwidth)
        self.__show_frameselection_frame('Start')

    def panel_select_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
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
        image_frame.grid(row=0, column=0, rowspan=3, **self.grid_fullwidth)
        self.__show_settings_frame('Start')

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
        if self.__get_save_recommendation(ask_to_apply=False):
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

    def show_about(self):
        """Show information about the application
        in a modal dialog
        """
        gui_commons.InfoDialog(
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
            gui_commons.InfoDialog(
                self.main_window,
                ('Errors:', '\n'.join(self.vars.errors)),
                title='Errors occurred!')
            self.vars.errors.clear()
        #

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
        self.widgets.action_area.grid(**self.grid_fullwidth)
        #
        # Set button states depending on the panel
        if self.vars.current_panel == PREVIEW:
            self.tkvars.buttonstate.previous.set(tkinter.NORMAL)
            self.tkvars.buttonstate.next_.set(tkinter.DISABLED)
            self.tkvars.buttonstate.apply.set(tkinter.NORMAL)
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
        else:
            if self.vars.current_panel == START_FRAME:
                self.tkvars.buttonstate.previous.set(tkinter.DISABLED)
            else:
                self.tkvars.buttonstate.previous.set(tkinter.NORMAL)
            #
            self.tkvars.buttonstate.next_.set(tkinter.NORMAL)
            self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
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
        self.widgets.buttons.apply = tkinter.Button(
            buttons_area,
            text='\u21ba Apply',
            command=self.do_apply_changes)
        self.widgets.buttons.apply.grid(row=1, column=0, **buttons_grid)
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
        show_heading(
            settings_frame,
            'Selection:',
            sticky=tkinter.W,
            columnspan=4)
        label = tkinter.Label(
            settings_frame,
            text='Tile size:')
        if fixed_tilesize:
            tilesize = tkinter.Label(
                settings_frame,
                textvariable=self.tkvars.selection.tilesize)
        else:
            tilesize = tkinter.Spinbox(
                settings_frame,
                from_=MINIMUM_TILESIZE,
                to=MAXIMUM_TILESIZE,
                increment=TILESIZE_INCREMENT,
                justify=tkinter.RIGHT,
                state='readonly',
                width=4,
                textvariable=self.tkvars.selection.tilesize)
        #
        label.grid(sticky=tkinter.W, column=0)
        tilesize.grid(
            sticky=tkinter.W,
            row=label.grid_info()['row'], column=1, columnspan=3)
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
            row=label.grid_info()['row'], column=1, columnspan=3)
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
            row=label.grid_info()['row'], column=1, columnspan=3)
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
            row=label.grid_info()['row'], column=1, columnspan=3)
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
            row=label.grid_info()['row'], column=1)
        label_sep.grid(
            sticky=tkinter.W,
            row=label.grid_info()['row'], column=2)
        center_y.grid(
            sticky=tkinter.W,
            row=label.grid_info()['row'], column=3)
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
            row=label.grid_info()['row'], column=1, columnspan=3)

    def __show_frameinfo(self,
                         parent_frame,
                         frame_position,
                         change_enabled=False):
        """Show information about the current video frame"""
        show_heading(
            parent_frame,
            'Original file:',
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
        show_heading(
            parent_frame,
            f'{frame_position} frame:',
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
                textvariable=self.tkvars.current_frame)
        #
        label.grid(sticky=tkinter.W)
        self.widgets.frame_number.grid(
            sticky=tkinter.W, columnspan=3,
            column=1, row=label.grid_info()['row'])
        if self.vars.vframe.display_ratio > 1:
            scale_factor = 'Size: scaled down (factor: %r)' % float(
                self.vars.vframe.display_ratio)
        else:
            scale_factor = 'Size: original dimensions'
        #
        label = tkinter.Label(parent_frame, text=scale_factor)
        label.grid(sticky=tkinter.W, columnspan=4)

    def __show_frameselection_frame(self, frame_position):
        """Show the settings frame"""
        frameselection_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        self.__show_frameinfo(
            frameselection_frame, frame_position, change_enabled=True)
        frameselection_frame.columnconfigure(4, weight=100)
        frameselection_frame.grid(row=0, column=1, **self.grid_fullwidth)

    def __show_settings_frame(self,
                              frame_position,
                              fixed_tilesize=False,
                              allowed_shapes=ALL_SHAPES):
        """Show the settings frame"""
        settings_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        self.__show_frameinfo(
            settings_frame, frame_position, change_enabled=False)
        self.__show_shape_settings(
            settings_frame,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes)
        show_heading(
            settings_frame,
            'Indicator colours:',
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
            row=label.grid_info()['row'], column=1, columnspan=3)
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
            row=label.grid_info()['row'], column=1, columnspan=3)
        settings_frame.columnconfigure(4, weight=100)
        settings_frame.grid(row=0, column=1, **self.grid_fullwidth)
        self.__do_toggle_height()

    def trigger_button_states(self, *unused_arguments):
        """Trigger undo, apply and save button states changes"""
        for (button_name, state_var) in self.tkvars.buttonstate.items():
            self.__do_update_button(button_name, state_var.get())
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
        self.vars.frame_file = FRAME_PATTERN % current_frame
        self.vars.vframe = pixelations.BaseImage(
            pathlib.Path(self.vars.original_frames.name)
            / self.vars.frame_file,
            canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        self.vars.tk_image = self.vars.vframe.tk_original
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
            self.vars.unapplied_changes = True
            self.tkvars.buttonstate.apply.set(tkinter.NORMAL)
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
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
    UserInterface(selected_file)


if __name__ == '__main__':
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
