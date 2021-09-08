#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

pixelate_image.py

Pixelate a part of an image
(Tkinter-based GUI assistant)

"""


import argparse
import logging
import mimetypes
import os
import pathlib
import sys
import tkinter

from tkinter import filedialog
from tkinter import messagebox

# local modules

import gui_commons
import pixelations


#
# Constants
#


SCRIPT_NAME = 'Partially pixelate an image'
HOMEPAGE = 'https://github.com/blackstream-x/pyxelate'
MAIN_WINDOW_TITLE = 'pyxelate: partially pixelate an image'

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
#

# Phases
CHOOSE_IMAGE = 'choose_image'
SELECT_AREA = 'select_area'

PHASES = (
    CHOOSE_IMAGE,
    SELECT_AREA)

PANEL_NAMES = {
    SELECT_AREA: 'Select area to be pixelated'}

CANVAS_WIDTH = 720
CANVAS_HEIGHT = 405

ELLIPSE = 'ellipse'
RECTANGLE = 'rectangle'

ELLIPTIC = 'elliptic'
RECTANGULAR = 'rectangular'

SHAPES = {ELLIPTIC: ELLIPSE, RECTANGULAR: RECTANGLE}

MINIMUM_TILESIZE = 10
MAXIMUM_TILESIZE = 200
TILESIZE_INCREMENT = 5

MINIMUM_SELECTION_SIZE = 20
INITIAL_SELECTION_SIZE = 50

SELECTION_SIZE_INCREMENT = 5

IMAGE_FILE_TYPES = [
    (suffix, mime_type) for (suffix, mime_type)
    in mimetypes.types_map.items()
    if mime_type.startswith('image/')]


#
# Helper Functions
#


...


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


class UserInterface():

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
        self.variables = Namespace(
            current_panel=None,
            disable_next_button=False,
            errors=[],
            tk_image=None,
            file_name=tkinter.StringVar(),
            image=None,
            original_path=file_path,
            target_path=tkinter.StringVar(),
            saved_height=0,
            panel_display=tkinter.StringVar(),
            trace=False,
            file_touched=False,
            px_image=Namespace(
                center_x=tkinter.IntVar(),
                center_y=tkinter.IntVar(),
                width=tkinter.IntVar(),
                height=tkinter.IntVar(),
                tilesize=tkinter.IntVar(),
                show_preview=tkinter.IntVar(),
                quadratic=tkinter.IntVar(),
                shape=tkinter.StringVar()),
            px_display=Namespace(
                center_x=0,
                center_y=0,
                width=0,
                height=0,
                color='red',
                shape=''),
            drag_data=Namespace(
                x=0,
                y=0,
                item=None),
            )
        # Trace changes to px_image variables
        for (_, variable) in self.variables.px_image.items():
            variable.trace_add('write', self.apply_changes)
        #
        self.widgets = Namespace(
            action_area=None,
            buttons_area=None,
            canvas=None,
            size_y=None)
        overview_frame = tkinter.Frame(self.main_window)
        file_label = tkinter.Label(
            overview_frame,
            text='Original file:')
        file_label.grid(
            padx=4, pady=2, row=0, column=0, sticky=tkinter.W)
        selected_file = tkinter.Entry(
            overview_frame,
            width=60,
            state=tkinter.DISABLED,
            textvariable=self.variables.file_name)
        selected_file.grid(
            padx=4, pady=2, row=0, column=1, sticky=tkinter.W)
        choose_button = tkinter.Button(
            overview_frame,
            text='Choose another …',
            command=self.do_choose_image)
        choose_button.grid(
            padx=4, pady=4, row=0, column=2, sticky=tkinter.W)
        panel_display = tkinter.Label(
            overview_frame,
            textvariable=self.variables.panel_display,
            justify=tkinter.LEFT)
        panel_display.grid(
            padx=4, pady=4, row=1, column=0, columnspan=3, sticky=tkinter.W)
        overview_frame.grid(**self.grid_fullwidth)
        self.do_choose_image(
            keep_existing=True,
            quit_on_empty_choice=True)
        self.main_window.mainloop()

    def do_choose_image(self,
                        keep_existing=False,
                        preset_path=None,
                        quit_on_empty_choice=False):
        """Choose an image via file dialog"""
        self.variables.current_panel = CHOOSE_IMAGE
        filetypes = [(label, f'*{suffix}') for (suffix, label)
                     in IMAGE_FILE_TYPES]
        file_path = self.variables.original_path
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
                    filetypes=filetypes,
                    parent=self.main_window)
                if not selected_file:
                    if quit_on_empty_choice:
                        self.quit()
                    #
                    return
                #
                file_path = pathlib.Path(selected_file)
            #
            # check for an image mime type,
            # and show an error dialog and retry
            # if the selected file is not an image
            file_type = mimetypes.guess_type(file_path)[0]
            if not file_type.startswith('image/'):
                messagebox.showerror(
                    'Not an image',
                    f'{file_path.name!r} is a file of type {file_type!r},'
                    ' but an image is required.',
                    icon=messagebox.ERROR)
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            if self.variables.file_touched:
                confirmation = messagebox.askyesno(
                    'Unsaved Changes',
                    'Discard the chages made to'
                    f' {self.variables.original_path.name!r}?',
                    icon=messagebox.WARNING)
                if not confirmation:
                    return
                #
            #
            # Set original_path and read image data
            self.do_load_image(file_path)
            break
        #
        self.next_panel()

    def do_load_image(self, file_path):
        """Load the image"""
        self.variables.original_path = file_path
        self.variables.image = pixelations.ImagePixelation(
            file_path, canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        (im_width, im_height) = self.variables.image.original.size
        # center selection
        self.variables.px_image.center_x.set(im_width // 2)
        self.variables.px_image.center_y.set(im_height // 2)
        # set selection sizes and reduce them
        # to the image dimensions if necessary
        sel_width = self.variables.px_image.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width,
            # rounded to SELECTION_SIZE_INCREMENT pixels
            sel_width = max(
                INITIAL_SELECTION_SIZE,
                round(im_width / (5 * SELECTION_SIZE_INCREMENT))
                * SELECTION_SIZE_INCREMENT)
        #
        self.variables.px_image.width.set(min(sel_width, im_width))
        sel_height = self.variables.px_image.height.get()
        if not sel_height:
            sel_height = sel_width
        #
        self.variables.px_image.height.set(min(sel_height, im_height))
        # set the shape
        if not self.variables.px_image.shape.get():
            self.variables.px_image.shape.set(ELLIPTIC)
        #
        # set tilesize
        if not self.variables.px_image.tilesize.get():
            self.variables.px_image.tilesize.set(
                pixelations.DEFAULT_TILESIZE)
        #
        # set the show_preview variable
        self.variables.px_image.show_preview.set(1)
        # set the displayed file name
        self.variables.file_name.set(file_path.name)
        self.variables.file_touched = False

    def show_shape_frame(self):
        """Show the shape frame"""
        shape_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        # First line
        line_frame = tkinter.Frame(shape_frame)
        label1 = tkinter.Label(
            line_frame,
            text='Pixelate the')
        shape_opts = tkinter.OptionMenu(
            line_frame,
            self.variables.px_image.shape,
            ELLIPTIC,
            RECTANGULAR)
        label2 = tkinter.Label(
            line_frame,
            text='area selected below using tiles measuring')
        tilesize = tkinter.Spinbox(
            line_frame,
            from_=10,
            to=MAXIMUM_TILESIZE,
            increment=TILESIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state='readonly',
            width=3,
            textvariable=self.variables.px_image.tilesize)
        label3 = tkinter.Label(
            line_frame,
            text='pixels each.')
        label1.grid(row=0, column=0)
        shape_opts.grid(row=0, column=1)
        label2.grid(row=0, column=2)
        tilesize.grid(row=0, column=3)
        label3.grid(row=0, column=4)
        line_frame.grid(sticky=tkinter.W)
        # Second line
        line_frame = tkinter.Frame(shape_frame)
        label1 = tkinter.Label(
            line_frame,
            text='Dimensions (width × height):')
        chain = tkinter.Checkbutton(
            line_frame,
            command=self.toggle_height,
            text='\u26d3',
            variable=self.variables.px_image.quadratic,
            indicatoron=0)
        size_x = tkinter.Spinbox(
            line_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.variables.image.original.width,
            increment=SELECTION_SIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.variables.px_image.width)
        label2 = tkinter.Label(
            line_frame,
            text=' × ')
        self.widgets.size_y = tkinter.Spinbox(
            line_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.variables.image.original.height,
            increment=SELECTION_SIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.variables.px_image.height)
        label3 = tkinter.Label(
            line_frame,
            text=', centered at position X:')
        center_x = tkinter.Spinbox(
            line_frame,
            from_=0,
            to=self.variables.image.original.width,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.variables.px_image.center_x)
        label4 = tkinter.Label(
            line_frame,
            text=', Y:')
        center_y = tkinter.Spinbox(
            line_frame,
            from_=0,
            to=self.variables.image.original.height,
            justify=tkinter.RIGHT,
            state='readonly',
            width=4,
            textvariable=self.variables.px_image.center_y)
        label1.grid(row=0, column=0)
        chain.grid(row=0, column=1)
        size_x.grid(row=0, column=2)
        label2.grid(row=0, column=3)
        self.widgets.size_y.grid(row=0, column=4)
        label3.grid(row=0, column=5)
        center_x.grid(row=0, column=6)
        label4.grid(row=0, column=7)
        center_y.grid(row=0, column=8)
        line_frame.grid(sticky=tkinter.W)
        shape_frame.grid(**self.grid_fullwidth)
        self.toggle_height()

    def do_save_file(self):
        """Save as the selected file"""
        original_suffix = self.variables.original_path.suffix
        filetypes = [
            (mimetypes.types_map[original_suffix], f'*{original_suffix}')]
        filetypes.extend(
            [(label, f'*{suffix}') for (suffix, label)
             in IMAGE_FILE_TYPES if suffix != original_suffix])
        selected_file = filedialog.asksaveasfilename(
            initialdir=str(self.variables.original_path.parent),
            defaultextension=original_suffix,
            filetypes=filetypes,
            parent=self.main_window,
            title='Save pixelated image as…')
        if not selected_file:
            return
        #
        logging.info('Saving the file as %r', selected_file)
        #  save the file and reset the "touched" flag
        self.variables.image.result.save(selected_file)
        self.variables.file_touched = False

    def panel_select_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.show_shape_frame()
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        if self.variables.image.display_ratio > 1:
            scale_factor = 'scaled down by factor %r' % float(
                self.variables.image.display_ratio)
        else:
            scale_factor = 'original size'
        #
        image_label = tkinter.Label(
            image_frame,
            text='Preview (%s)' % scale_factor)
        image_label.grid(sticky=tkinter.W)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.variables.tk_image = self.variables.image.get_tk_image(
            self.variables.image.original)
        self.widgets.canvas.create_image(
            0, 0,
            image=self.variables.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.grid()
        self.draw_selector()
        self.apply_pixelation()
        self.variables.trace = True
        image_frame.grid(**self.grid_fullwidth)

    def toggle_height(self):
        """Toggle height spinbox to follow width"""
        if self.variables.px_image.quadratic.get():
            self.widgets.size_y.config(
                state=tkinter.DISABLED,
                textvariable=self.variables.px_image.width)
        else:
            self.widgets.size_y.config(
                state='readonly',
                textvariable=self.variables.px_image.height)
        #

    def apply_pixelation(self):
        """Apply the pixelation to the image and update the preview"""
        self.variables.image.set_tilesize(
            self.variables.px_image.tilesize.get())
        width = self.variables.px_image.width.get()
        if self.variables.px_image.quadratic.get():
            height = width
        else:
            height = self.variables.px_image.height.get()
        #
        self.variables.image.set_shape(
            (self.variables.px_image.center_x.get(),
             self.variables.px_image.center_y.get()),
            SHAPES[self.variables.px_image.shape.get()],
            (width, height))
        self.show_preview()

    def show_preview(self):
        """Update the preview"""
        if self.variables.px_image.show_preview.get():
            self.widgets.canvas.delete('image')
            self.variables.tk_image = self.variables.image.get_tk_image(
                self.variables.image.result)
            self.widgets.canvas.create_image(
                0, 0,
                image=self.variables.tk_image,
                anchor=tkinter.NW,
                tags='image')
            self.widgets.canvas.tag_lower('image', 'selector')
        #

    def draw_selector(self):
        """Draw the pixelation selector on the canvas,
        its coordinates determined by the px_* variables
        """
        for key in ('center_x', 'center_y', 'width', 'height'):
            self.variables.px_display[key] = \
                self.variables.image.to_display_size(
                    self.variables.px_image[key].get())
        if self.variables.px_image.quadratic.get():
            self.variables.px_display.height = self.variables.px_display.width
        #
        left = self.variables.px_display.center_x - \
            self.variables.px_display.width // 2
        right = left + self.variables.px_display.width
        top = self.variables.px_display.center_y - \
            self.variables.px_display.height // 2
        bottom = top + self.variables.px_display.height
        self.variables.px_display.shape = \
            self.variables.px_image.shape.get()
        #
        # logging.info('Display: %r', self.variables.px_display.items())
        self.widgets.canvas.delete('selector')
        if self.variables.px_display.shape == ELLIPTIC:
            create_widget = self.widgets.canvas.create_oval
        elif self.variables.px_display.shape == RECTANGULAR:
            create_widget = self.widgets.canvas.create_rectangle
        #
        create_widget(
            left, top, right, bottom,
            outline=self.variables.px_display.color,
            fill=self.variables.px_display.color,
            stipple='gray12',
            tags='selector')
        # add bindings to drag the selector over the image
        self.widgets.canvas.tag_bind(
            "selector", "<ButtonPress-1>", self.drag_start)
        self.widgets.canvas.tag_bind(
            "selector", "<ButtonRelease-1>", self.drag_stop)
        self.widgets.canvas.tag_bind(
            "selector", "<B1-Motion>", self.drag)

    def apply_changes(self, *unused_arguments):
        """Apply changes if trace is active"""
        if self.variables.trace:
            self.variables.file_touched = True
            self.apply_pixelation()
            self.draw_selector()
        #

    def drag_start(self, event):
        """Begining drag of an object"""
        # record the item and its location
        self.variables.drag_data["item"] = 'selector'
        self.variables.drag_data["x"] = event.x
        self.variables.drag_data["y"] = event.y

    def drag_stop(self, *unused_event):
        """End drag of an object"""
        # reset the drag information
        self.variables.drag_data["item"] = None
        self.variables.drag_data["x"] = 0
        self.variables.drag_data["y"] = 0
        # Update pixelation center
        bbox = self.widgets.canvas.bbox('selector')
        center_x = self.variables.image.from_display_size(
            (bbox[0] + bbox[2]) // 2)
        center_y = self.variables.image.from_display_size(
            (bbox[1] + bbox[3]) // 2)
        self.variables.trace = False
        self.variables.px_image.center_x.set(center_x)
        self.variables.px_image.center_y.set(center_y)
        self.variables.file_touched = True
        self.apply_pixelation()
        self.variables.trace = True

    def drag(self, event):
        """Handle dragging of an object"""
        # compute how much the mouse has moved
        delta_x = event.x - self.variables.drag_data["x"]
        delta_y = event.y - self.variables.drag_data["y"]
        # move the object the appropriate amount
        self.widgets.canvas.move(
            self.variables.drag_data["item"], delta_x, delta_y)
        # record the new position
        self.variables.drag_data["x"] = event.x
        self.variables.drag_data["y"] = event.y

    def next_action(self):
        """Execute the next action"""
        current_index = PHASES.index(self.variables.current_panel)
        next_index = current_index + 1
        try:
            next_phase = PHASES[next_index]
        except IndexError as error:
            raise ValueError(
                f'Phase number #{next_index} out of range') from error
        #
        method_display = (
            f'Action method for phase #{next_index} ({next_phase})')
        method_name = f'do_{next_phase})'
        try:
            action_method = getattr(self, method_name)
        except AttributeError:
            logging.warning('%s is undefined', method_display)
        else:
            try:
                action_method()
            except NotImplementedError as error:
                raise ValueError(
                    f'{method_display} has not been implemented yet') \
                    from error
            #
        #
        self.variables.current_phase = next_phase

    def next_panel(self):
        """Execute the next action and go to the next panel"""
        try:
            self.next_action()
        except ValueError as error:
            self.variables.errors.append(str(error))
        #
        self.__show_panel()

    def previous_panel(self):
        """Go to the next panel"""
        phase_name = self.variables.current_panel
        phase_index = PHASES.index(phase_name)
        method_display = (
            f'Rollback method for phase #{phase_index} ({phase_name})')
        method_name = f'rollback_{phase_name})'
        try:
            rollback_method = getattr(self, method_name)
        except AttributeError:
            logging.warning('%s is undefined', method_display)
        else:
            self.variables.current_phase = PHASES[phase_index - 1]
            try:
                rollback_method()
            except NotImplementedError:
                self.variables.errors.append(
                    f'{method_display} has not been implemented yet')
            #
        #
        self.__show_panel()

    def quit(self, event=None):
        """Exit the application"""
        del event
        if self.variables.file_touched:
            confirmation = messagebox.askyesno(
                'Unsaved Changes',
                'Discard the chages made to'
                f' {self.variables.original_path.name!r}?',
                icon=messagebox.WARNING)
            if not confirmation:
                return
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
            ('License:', LICENSE_TEXT),
            title='About…')
        #

    def __show_errors(self):
        """Show errors if there are any"""
        if self.variables.errors:
            errors_frame = tkinter.Frame(
                self.widgets.action_area,
                **self.with_border)
            for message in self.variables.errors:
                error_value = tkinter.Label(
                    errors_frame,
                    text=message,
                    justify=tkinter.LEFT)
                error_value.grid(
                    padx=4,
                    sticky=tkinter.W)
            #
            self.variables.errors.clear()
            errors_frame.grid(**self.grid_fullwidth)
        #

    def __show_panel(self):
        """Show a panel.
        Add the "Previous", "Next", "Choose another relase",
        "About" and "Quit" buttons at the bottom
        """
        for area in ('action_area', 'buttons_area'):
            try:
                self.widgets[area].grid_forget()
            except AttributeError:
                pass
            #
        #
        self.widgets.action_area = tkinter.Frame(self.main_window)
        try:
            panel_method = getattr(
                self,
                'panel_%s' % self.variables.current_phase)
        except AttributeError:
            self.variables.errors.append(
                'Panel for Phase %r has not been implemented yet,'
                ' going back to phase %r.' % (
                    self.variables.current_phase,
                    self.variables.current_panel))
            self.variables.current_phase = self.variables.current_panel
            panel_method = getattr(
                self,
                'panel_%s' % self.variables.current_phase)
            self.variables.disable_next_button = False
        else:
            self.variables.current_panel = self.variables.current_phase
        #
        self.variables.panel_display.set(
            '%s (panel %s of %s)' % (
                PANEL_NAMES[self.variables.current_panel],
                PHASES.index(self.variables.current_panel),
                len(PHASES) - 1))
        self.__show_errors()
        panel_method()
        self.widgets.action_area.grid(**self.grid_fullwidth)
        #
        self.widgets.buttons_area = tkinter.Frame(
            self.main_window,
            **self.with_border)
        #
        buttons_grid = dict(padx=5, pady=5, row=0)
        if self.variables.disable_next_button or \
                self.variables.current_phase == SELECT_AREA:
            next_button_state = tkinter.DISABLED
        else:
            next_button_state = tkinter.NORMAL
        #
        self.variables.disable_next_button = False
        next_button = tkinter.Button(
            self.widgets.buttons_area,
            text='\u25b7 Next',
            command=self.next_panel,
            state=next_button_state)
        next_button.grid(column=0, sticky=tkinter.W, **buttons_grid)
        apply_button = tkinter.Button(
            self.widgets.buttons_area,
            text='Apply and continue',
            command=self.variables.image.apply_result)
        apply_button.grid(column=1, sticky=tkinter.W, **buttons_grid)
        save_button = tkinter.Button(
            self.widgets.buttons_area,
            text='Save as…',
            command=self.do_save_file)
        save_button.grid(column=2, sticky=tkinter.W, **buttons_grid)
        about_button = tkinter.Button(
            self.widgets.buttons_area,
            text='About…',
            command=self.show_about)
        about_button.grid(column=4, sticky=tkinter.E, **buttons_grid)
        quit_button = tkinter.Button(
            self.widgets.buttons_area,
            text='Quit',
            command=self.quit)
        quit_button.grid(column=5, sticky=tkinter.E, **buttons_grid)
        self.widgets.buttons_area.columnconfigure(3, weight=100)
        self.widgets.buttons_area.grid(**self.grid_fullwidth)


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
