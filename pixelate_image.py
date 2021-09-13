#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""

pixelate_image.py

Pixelate a part of an image
(Tkinter-based GUI assistant)

"""


import argparse
import logging
import os
import pathlib
import sys
import time
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

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 640

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

MINIMUM_TILESIZE = 10
MAXIMUM_TILESIZE = 200
TILESIZE_INCREMENT = 5

MINIMUM_SELECTION_SIZE = 20
INITIAL_SELECTION_SIZE = 50

POSSIBLE_INDICATOR_COLORS = (
    'white', 'black', 'red', 'green', 'blue', 'cyan', 'yellow', 'magenta')

UNDO_SIZE = 20

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
        if self.effective_values['shape'] in (CIRCLE, SQUARE):
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
        open_support, save_support = pixelations.get_supported_extensions()
        logging.debug('File formats open support: %r', open_support)
        logging.debug('File formats save support: %r', save_support)
        self.main_window = tkinter.Tk()
        self.main_window.title(MAIN_WINDOW_TITLE)
        self.vars = Namespace(
            open_support=sorted(open_support),
            save_support=sorted(save_support),
            current_panel=None,
            disable_next_button=False,
            errors=[],
            tk_image=None,
            image=None,
            original_path=file_path,
            trace=False,
            file_touched=False,
            undo_buffer=[],
            drag_data=Namespace(
                x=0,
                y=0,
                item=None),
            )
        self.tkvars = Namespace(
            file_name=tkinter.StringVar(),
            show_preview=tkinter.IntVar(),
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
            )
        # Trace changes:
        # … to selection variables
        for (_, variable) in self.tkvars.selection.items():
            variable.trace_add('write', self.trigger_selection_change)
        #
        # TODO: … to the disable_buttons variables
        # for (_, variable) in self.tkvars.disable_buttons.items():
        #     variable.trace_add('write', self.trigger_button_states)
        #
        # … to the indicator.color variable
        self.tkvars.indicator.drag_color.set('blue')
        self.tkvars.indicator.color.set('red')
        self.tkvars.indicator.color.trace_add(
            'write', self.trigger_indicator_redraw)
        #
        self.widgets = Namespace(
            action_area=None,
            # buttons_area=None,
            buttons=Namespace(
                undo=None,
                apply=None,
                save=None),
            canvas=None,
            height=None)
        self.do_choose_image(
            keep_existing=True,
            quit_on_empty_choice=True)
        self.main_window.protocol('WM_DELETE_WINDOW', self.quit)
        self.main_window.mainloop()

    def do_choose_image(self,
                        keep_existing=False,
                        preset_path=None,
                        quit_on_empty_choice=False):
        """Choose an image via file dialog"""
        self.vars.current_panel = CHOOSE_IMAGE
        filetypes = [('Supported image files', f'*{suffix}') for suffix
                     in self.vars.open_support] + [('All files', '*.*')]
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
            # check for an supported file type,
            # and show an error dialog and retry
            # if the selected file is not an image
            if file_path.suffix not in self.vars.open_support:
                messagebox.showerror(
                    'Unsupported file type',
                    f'{file_path.name!r} is not a supported image file.',
                    icon=messagebox.ERROR)
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            if self.vars.file_touched:
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
            self.do_load_image(file_path)
            break
        #
        self.next_panel()

    def do_load_image(self, file_path):
        """Load the image"""
        self.vars.original_path = file_path
        self.vars.image = pixelations.ImagePixelation(
            file_path, canvas_size=(CANVAS_WIDTH, CANVAS_HEIGHT))
        (im_width, im_height) = self.vars.image.original.size
        # center selection
        self.tkvars.selection.center_x.set(im_width // 2)
        self.tkvars.selection.center_y.set(im_height // 2)
        # set selection sizes and reduce them
        # to the image dimensions if necessary
        sel_width = self.tkvars.selection.width.get()
        if not sel_width:
            # Set initial selection width to 20% of image width
            sel_width = max(
                INITIAL_SELECTION_SIZE,
                round(im_width / 5))
        #
        self.tkvars.selection.width.set(min(sel_width, im_width))
        sel_height = self.tkvars.selection.height.get()
        if not sel_height:
            sel_height = sel_width
        #
        self.tkvars.selection.height.set(min(sel_height, im_height))
        # set the shape
        if not self.tkvars.selection.shape.get():
            self.tkvars.selection.shape.set(OVAL)
        #
        # set tilesize
        if not self.tkvars.selection.tilesize.get():
            self.tkvars.selection.tilesize.set(
                pixelations.DEFAULT_TILESIZE)
        #
        # set the show_preview variable by default
        self.tkvars.show_preview.set(1)
        # set the displayed file name
        self.tkvars.file_name.set(file_path.name)
        self.vars.file_touched = False

    def do_apply_changes(self, interactive_mode=True):
        """Apply changes to the image"""
        # Rrecord the position, shape, size,
        # and tilesize of the selection, and append that together with
        # the current image as a tuple to the undo buffer
        self.vars.undo_buffer.append(
            (self.vars.image.original,
             FrozenSelection(self.tkvars.selection)))
        if len(self.vars.undo_buffer) > UNDO_SIZE:
            del self.vars.undo_buffer[:-UNDO_SIZE]
        #
        # Visual feedback in interactive mode
        if interactive_mode:
            self.draw_indicator(stipple='gray75')
            self.main_window.update_idletasks()
            time.sleep(.2)
            self.draw_indicator()
        #
        self.vars.image.set_original(self.vars.image.result)
        # TODO: deactivate "Apply" button
        self.trigger_preview_toggle()

    def do_save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        # Compare the position, shape, size,
        # and tilesize of the selection
        # with the ones recorded at applying time.
        # If they differ, and the preview is active, ask
        # if the currently previewed pixelation should be applied
        # (WYSIWYG approach)
        try:
            last_applied_selection = self.vars.undo_buffer[-1][1]
        except IndexError:
            # Empty undo buffer
            undo_buffer_empty = True
        else:
            undo_buffer_empty = False
            current_selection = FrozenSelection(self.tkvars.selection)
            if current_selection != last_applied_selection:
                self.vars.file_touched = True
            #
        #
        if self.vars.file_touched and \
                self.tkvars.show_preview.get():
            if messagebox.askyesno(
                    'Not yet applied changes',
                    'Pixelate the current selection before saving?'):
                self.do_apply_changes(interactive_mode=False)
            elif undo_buffer_empty:
                messagebox.showinfo(
                    'Image unchanged', 'Nothing to save in this case.')
                return False
            #
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
        logging.info('Saving the file as %r', selected_file)
        #  save the file and reset the "touched" flag
        self.vars.image.original.save(selected_file)
        self.vars.original_path = pathlib.Path(selected_file)
        self.tkvars.file_name.set(self.vars.original_path.name)
        self.vars.undo_buffer.clear()
        # self.update_ ??? FIXME
        # TODO: deactivate "Save" button
        self.vars.file_touched = False
        return True

    def show_settings_frame(self):
        """Show the shape frame"""
        settings_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        heading = tkinter.Label(
            settings_frame,
            font=(None, 11, 'bold'),
            text='Original file:')
        heading.grid(sticky=tkinter.W, columnspan=4)
        label = tkinter.Label(
            settings_frame,
            textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            settings_frame,
            text='Choose another file',
            command=self.do_choose_image)
        choose_button.grid(sticky=tkinter.W, columnspan=4)
        heading = tkinter.Label(
            settings_frame,
            font=(None, 11, 'bold'),
            text='Display:')
        heading.grid(sticky=tkinter.W, columnspan=4)
        if self.vars.image.display_ratio > 1:
            scale_factor = 'Size: scaled down (factor: %r)' % float(
                self.vars.image.display_ratio)
        else:
            scale_factor = 'Size: original dimensions'
        #
        label = tkinter.Label(settings_frame, text=scale_factor)
        label.grid(sticky=tkinter.W, columnspan=4)
        heading = tkinter.Label(
            settings_frame,
            font=(None, 11, 'bold'),
            text='Selection:')
        heading.grid(sticky=tkinter.W, columnspan=4)
        label = tkinter.Label(
            settings_frame,
            text='Tile size:')
        tilesize = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_TILESIZE,
            to=MAXIMUM_TILESIZE,
            increment=TILESIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state='readonly',
            width=3,
            textvariable=self.tkvars.selection.tilesize)
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
            OVAL, CIRCLE, RECT, SQUARE)
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
            command=self.show_image,
            text='active',
            variable=self.tkvars.show_preview,
            indicatoron=1)
        label.grid(sticky=tkinter.W, column=0)
        preview_active.grid(
            sticky=tkinter.W,
            row=label.grid_info()['row'], column=1, columnspan=3)
        heading = tkinter.Label(
            settings_frame,
            font=(None, 11, 'bold'),
            text='Colours:')
        heading.grid(sticky=tkinter.W, columnspan=4)
        label = tkinter.Label(
            settings_frame,
            text='Current selection:')
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
            text='New selection:')
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
        self.toggle_height()

    def panel_select_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.show_settings_frame()
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=CANVAS_WIDTH,
            height=CANVAS_HEIGHT)
        self.vars.tk_image = self.vars.image.get_tk_image(
            self.vars.image.original)
        self.widgets.canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.grid()
        self.draw_indicator()
        self.apply_pixelation()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.tag_bind(
            'image', "<ButtonPress-1>", self.new_selection_drag_start)
        self.widgets.canvas.tag_bind(
            'image', "<ButtonRelease-1>", self.new_selection_drag_stop)
        self.widgets.canvas.tag_bind(
            'image', "<B1-Motion>", self.new_selection_drag)
        image_frame.grid(row=0, column=0, rowspan=3, **self.grid_fullwidth)

    def toggle_height(self):
        """Toggle height spinbox to follow width"""
        if not self.widgets.height:
            return
        #
        if self.tkvars.selection.shape.get() in (CIRCLE, SQUARE):
            self.widgets.height.config(
                state=tkinter.DISABLED,
                textvariable=self.tkvars.selection.width)
        else:
            self.widgets.height.config(
                state='readonly',
                textvariable=self.tkvars.selection.height)
        #

    def apply_pixelation(self):
        """Apply the pixelation to the image and update the preview"""
        self.vars.image.set_tilesize(
            self.tkvars.selection.tilesize.get())
        width = self.tkvars.selection.width.get()
        if self.tkvars.selection.shape.get() in (CIRCLE, SQUARE):
            height = width
        else:
            height = self.tkvars.selection.height.get()
        #
        self.vars.image.set_shape(
            (self.tkvars.selection.center_x.get(),
             self.tkvars.selection.center_y.get()),
            SHAPES[self.tkvars.selection.shape.get()],
            (width, height))
        self.show_image()

    def show_image(self):
        """Show image or preview according to the show_preview setting"""
        if self.tkvars.show_preview.get():
            source_image = self.vars.image.result
        else:
            source_image = self.vars.image.original
        #
        self.widgets.canvas.delete('image')
        self.vars.tk_image = self.vars.image.get_tk_image(
            source_image)
        self.widgets.canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.tag_lower('image', 'indicator')

    def draw_indicator(self, stipple='gray12'):
        """Draw the pixelation selector on the canvas,
        its coordinates determined by the px_* variables
        """
        width = self.vars.image.to_display_size(
            self.tkvars.selection.width.get())
        if self.tkvars.selection.shape.get() in (CIRCLE, SQUARE):
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
        self.widgets.canvas.delete('indicator')
        if shape in (OVAL, CIRCLE):
            create_widget = self.widgets.canvas.create_oval
        elif shape in (RECT, SQUARE):
            create_widget = self.widgets.canvas.create_rectangle
        #
        current_color = self.tkvars.indicator.color.get()
        create_widget(
            left, top, right, bottom,
            outline=current_color,
            fill=current_color,
            stipple=stipple,
            tags='indicator')
        # add bindings to drag the selector over the image
        self.widgets.canvas.tag_bind(
            'indicator', "<ButtonPress-1>", self.indicator_drag_start)
        self.widgets.canvas.tag_bind(
            'indicator', "<ButtonRelease-1>", self.indicator_drag_stop)
        self.widgets.canvas.tag_bind(
            'indicator', "<B1-Motion>", self.indicator_drag)

    def trigger_selection_change(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.vars.file_touched = True
            self.apply_pixelation()
            self.draw_indicator()
        #
        self.toggle_height()

    def trigger_preview_toggle(self, *unused_arguments):
        """Trigger preview update"""
        try:
            self.show_image()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def trigger_indicator_redraw(self, *unused_arguments):
        """Trigger redrawing of the indicator"""
        try:
            self.draw_indicator()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def indicator_drag_start(self, event):
        """Begining drag of the indicator"""
        # record the item and its location
        self.vars.drag_data["item"] = 'indicator'
        self.vars.drag_data["x"] = event.x
        self.vars.drag_data["y"] = event.y

    def indicator_drag(self, event):
        """Handle dragging of the indicator"""
        # compute how much the mouse has moved
        delta_x = event.x - self.vars.drag_data["x"]
        delta_y = event.y - self.vars.drag_data["y"]
        # move the object the appropriate amount
        self.widgets.canvas.move(
            self.vars.drag_data["item"], delta_x, delta_y)
        # record the new position
        self.vars.drag_data["x"] = event.x
        self.vars.drag_data["y"] = event.y
        # Update pixelation center
        bbox = self.widgets.canvas.bbox('indicator')
        center_x = self.vars.image.from_display_size(
            (bbox[0] + bbox[2]) // 2)
        center_y = self.vars.image.from_display_size(
            (bbox[1] + bbox[3]) // 2)
        # Set the center coordinates
        self.vars.trace = False
        self.tkvars.selection.center_x.set(center_x)
        self.tkvars.selection.center_y.set(center_y)
        self.vars.trace = True

    def indicator_drag_stop(self, *unused_event):
        """End drag of an object"""
        # reset the drag information
        self.vars.drag_data["item"] = None
        self.vars.drag_data["x"] = 0
        self.vars.drag_data["y"] = 0
        # Trigger the selection change explicitly
        self.trigger_selection_change()

    def new_selection_drag_start(self, event):
        """Begining dragging for a new selection"""
        # record the item and its location
        self.vars.drag_data["item"] = 'size'
        self.vars.drag_data["x"] = event.x
        self.vars.drag_data["y"] = event.y

    def new_selection_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        bbox = self.widgets.canvas.bbox('size')
        if not bbox:
            return
        #
        self.widgets.canvas.delete('size')
        left, top, right, bottom = bbox
        center_x = self.vars.image.from_display_size((left + right) // 2)
        center_y = self.vars.image.from_display_size((top + bottom) // 2)
        width = self.vars.image.from_display_size(right - left)
        height = self.vars.image.from_display_size(bottom - top)
        if width < MINIMUM_SELECTION_SIZE:
            width = MINIMUM_SELECTION_SIZE
        #
        if height < MINIMUM_SELECTION_SIZE:
            height = MINIMUM_SELECTION_SIZE
        #
        # Set the selection attributes
        self.vars.trace = False
        self.tkvars.selection.center_x.set(center_x)
        self.tkvars.selection.center_y.set(center_y)
        self.tkvars.selection.width.set(width)
        self.tkvars.selection.height.set(height)
        self.vars.trace = True
        # TODO: Adjust to minimum sizes
        # Trigger the selection change explicitly
        self.trigger_selection_change()

    def new_selection_drag(self, event):
        """Drag a new selection"""
        current_x = event.x
        current_y = event.y
        [left, right] = sorted((current_x, self.vars.drag_data["x"]))
        [top, bottom] = sorted((current_y, self.vars.drag_data["y"]))
        # Respect "quadratic" shapes
        if self.tkvars.selection.shape.get() in (CIRCLE, SQUARE):
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
        self.widgets.canvas.delete('size')
        outer_dash = (1, 1)
        shape = self.tkvars.selection.shape.get()
        current_color = self.tkvars.indicator.drag_color.get()
        if shape in (OVAL, CIRCLE):
            outer_dash = (5, 5)
        #
        self.widgets.canvas.create_rectangle(
            left, top, right, bottom,
            dash=outer_dash,
            outline=current_color,
            tags='size')
        if shape in (OVAL, CIRCLE):
            self.widgets.canvas.create_oval(
                left, top, right, bottom,
                dash=(1, 1),
                outline=current_color,
                tags='size')
        left, top, right, bottom = self.widgets.canvas.bbox('size')
        center_x = self.vars.image.from_display_size((left + right) // 2)
        center_y = self.vars.image.from_display_size((top + bottom) // 2)
        width = self.vars.image.from_display_size(right - left)
        height = self.vars.image.from_display_size(bottom - top)
        # Set the selection attributes
        self.vars.trace = False
        self.tkvars.selection.center_x.set(center_x)
        self.tkvars.selection.center_y.set(center_y)
        self.tkvars.selection.width.set(width)
        self.tkvars.selection.height.set(height)
        self.vars.trace = True

    def next_action(self):
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
        self.vars.current_phase = next_phase

    def next_panel(self):
        """Execute the next action and go to the next panel"""
        try:
            self.next_action()
        except ValueError as error:
            self.vars.errors.append(str(error))
        #
        self.__show_panel()

    def previous_panel(self):
        """Go to the next panel"""
        phase_name = self.vars.current_panel
        phase_index = PHASES.index(phase_name)
        method_display = (
            f'Rollback method for phase #{phase_index} ({phase_name})')
        method_name = f'rollback_{phase_name})'
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
        try:
            last_applied_selection = self.vars.undo_buffer[-1][1]
        except IndexError:
            # Empty undo buffer
            pass
        else:
            current_selection = FrozenSelection(self.tkvars.selection)
            if current_selection != last_applied_selection and \
                    self.tkvars.show_preview.get():
                self.vars.file_touched = True
            #
        #
        if self.vars.file_touched:
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
            self.vars.disable_next_button = False
        else:
            self.vars.current_panel = self.vars.current_phase
        #
        self.__show_errors()
        panel_method()
        self.widgets.action_area.grid(**self.grid_fullwidth)
        #
        buttons_area = tkinter.Frame(self.widgets.action_area)
        #
        buttons_grid = dict(padx=5, pady=5)
        undo_button = tkinter.Button(
            buttons_area,
            text='\u21b6 Undo',
            command=self.next_panel)
        undo_button.grid(row=0, column=0, sticky=tkinter.E, **buttons_grid)
        logging.info('Undo button state: %r', undo_button.cget('state'))
        apply_button = tkinter.Button(
            buttons_area,
            text='\u2713 Apply',
            command=self.do_apply_changes)
        apply_button.grid(row=0, column=1, sticky=tkinter.E, **buttons_grid)
        save_button = tkinter.Button(
            buttons_area,
            text='\U0001f5ab Save',
            command=self.do_save_file)
        save_button.grid(row=0, column=2, sticky=tkinter.E, **buttons_grid)
        about_button = tkinter.Button(
            buttons_area,
            text='\u24d8 About',
            command=self.show_about)
        about_button.grid(row=1, column=0, sticky=tkinter.E, **buttons_grid)
        quit_button = tkinter.Button(
            buttons_area,
            text='\u23fb Quit',
            command=self.quit)
        quit_button.grid(row=1, column=2, sticky=tkinter.E, **buttons_grid)
        self.widgets.action_area.rowconfigure(1, weight=100)
        buttons_area.grid(row=2, column=1, sticky=tkinter.E)


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
