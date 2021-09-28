# -*- coding: utf-8 -*-

"""

app.py

Common application parts of the pyxelate scripts

Copyright (C) 2021 Rainer Schwarzbach

This file is part of pyxelate.

pyxelate is free software: you can redistribute it and/or modify
it under the terms of the MIT License.

pyxelate is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
See the LICENSE file for more details.

"""


import json
import logging
import os
import pathlib
import sys
import time
import tkinter

from tkinter import filedialog
from tkinter import messagebox

# local modules

from pyxelate import gui
from pyxelate import pixelations


#
# Constants
#


#WINDOW_TITLE = 'pyxelate: ???'

# =============================================================================
# with open(SCRIPT_PATH.parent /
#           'docs' /
#           f'{SCRIPT_PATH.stem}_help.json') as help_file:
#     HELP = json.load(help_file)
# #
# =============================================================================

# =============================================================================
# # Phases
# CHOOSE_IMAGE = 'choose_image'
# SELECT_AREA = 'select_area'
#
# PHASES = (
#     CHOOSE_IMAGE,
#     SELECT_AREA)
#
# PANEL_NAMES = {
#     SELECT_AREA: 'Select area to be pixelated'}
# =============================================================================

# =============================================================================
# CANVAS_WIDTH = 900
# CANVAS_HEIGHT = 640
# =============================================================================

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

INDICATOR_OUTLINE_WIDTH = 2

POSSIBLE_INDICATOR_COLORS = (
    'white', 'black', 'red', 'green', 'blue', 'cyan', 'yellow', 'magenta')

# =============================================================================
# UNDO_SIZE = 20
# =============================================================================

# =============================================================================
# HEADINGS_FONT = (None, 10, 'bold')
# =============================================================================

# Items drawn on the canvas
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



class InterfacePlugin:

    """Class instantiated with the UserInterface
    to access its varuables and widgets
    """

    def __init__(self, ui_instance):
        """Store the ui_instance"""
        self.ui_instance = ui_instance
        self.tkvars = ui_instance.tkvars
        self.vars = ui_instance.vars
        self.widgets = ui_instance.widgets
        self.main_window = ui_instance.main_window


class Callbacks(InterfacePlugin):

    """Callback methods"""

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

    def __get_bbox_selection(self, tag_name):
        """Get the bbox selection as a Namespace with the
        selection coordinates (center and dimensions),
        calculated from display to image size.
        Return a tuple of (width, height, center_x, center_y)
        """
        left, top, right, bottom = self.widgets.canvas.bbox(tag_name)
        width = self.vars.image.from_display_size(right - left)
        height = self.vars.image.from_display_size(bottom - top)
        center_x = self.vars.image.from_display_size((left + right) // 2)
        center_y = self.vars.image.from_display_size((top + bottom) // 2)
        return (width, height, center_x, center_y)

    def indicator_drag_move(self, event):
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
        (center_x, center_y) = self.__get_bbox_selection(INDICATOR)[-2:]
        self.ui_instance.do_update_selection(
            center_x=center_x,
            center_y=center_y)
        return True

    def indicator_drag_start(self, event):
        """Begining drag of the indicator"""
        # record the item and its location
        self.vars.drag_data.item = INDICATOR
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def indicator_drag_stop(self, *unused_event):
        """End drag of an object"""
        # reset the drag information
        self.vars.drag_data.item = None
        self.vars.drag_data.x = 0
        self.vars.drag_data.y = 0
        # Trigger the selection change explicitly
        self.trigger_selection_change()
        return True

    def selection_drag_move(self, event):
        """Drag a new selection"""
        if self.vars.drag_data.item == INDICATOR:
            return self.indicator_drag_move(event)
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
        (width, height, center_x, center_y) = \
            self.__get_bbox_selection(NEW_SELECTION)
        self.ui_instance.do_update_selection(
            center_x=center_x,
            center_y=center_y,
            width=width,
            height=height)
        return True

    def selection_drag_start(self, event):
        """Begining dragging for a new selection"""
        # record the item and its location
        if self.__clicked_inside_indicator(event):
            return self.indicator_drag_start(event)
        #
        self.vars.drag_data.item = NEW_SELECTION
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def selection_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        if self.vars.drag_data.item == INDICATOR:
            return self.indicator_drag_stop()
        #
        try:
            (width, height, center_x, center_y) = \
                self.__get_bbox_selection(NEW_SELECTION)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(NEW_SELECTION)
        # Adjust to minimum sizes
        if width < MINIMUM_SELECTION_SIZE:
            width = MINIMUM_SELECTION_SIZE
        #
        if height < MINIMUM_SELECTION_SIZE:
            height = MINIMUM_SELECTION_SIZE
        #
        # Set the selection attributes
        self.ui_instance.do_update_selection(
            center_x=center_x,
            center_y=center_y,
            width=width,
            height=height)
        # Trigger the selection change explicitly
        self.trigger_selection_change()
        return True

    def trigger_indicator_redraw(self, *unused_arguments):
        """Trigger redrawing of the indicator"""
        try:
            self.ui_instance.do_draw_indicator()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def trigger_preview_toggle(self, *unused_arguments):
        """Trigger preview update"""
        try:
            self.ui_instance.do_show_image()
        except AttributeError as error:
            logging.warning('%s', error)
        #

    def trigger_selection_change(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.vars.unapplied_changes = True
            self.tkvars.buttonstate.apply.set(tkinter.NORMAL)
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
            self.ui_instance.do_pixelate()
            self.ui_instance.do_draw_indicator()
        #
        self.ui_instance.do_toggle_height()


class Panels(InterfacePlugin):

    """Panel and panel component methods"""

    ...

    def component_shape_settings(self,
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
            return self.ui_instance.show_help('Selection')
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

    def component_file_info(self, parent_frame):
        """Show information about the current file"""
        heading = gui.Heading(
            parent_frame,
            text='Original file:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.ui_instance.show_help('Original file')
        #
        help_button = tkinter.Button(
            parent_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
        label = tkinter.Label(
            parent_frame,
            textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            parent_frame,
            text='Choose another file',
            command=self.ui_instance.do_load_file)
        choose_button.grid(sticky=tkinter.W, columnspan=4)

    def component_image_info(self,
                             parent_frame,
                             frame_position,
                             change_enabled=False):
        """Show information about the current image"""
        raise NotImplementedError

    def sidebar_settings(self,
                         frame_position,
                         fixed_tilesize=False,
                         allowed_shapes=ALL_SHAPES):
        """Show the settings sidebar"""
        settings_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        self.component_file_info(settings_frame)
        self.component_image_info(
            settings_frame, frame_position, change_enabled=False)
        self.component_shape_settings(
            settings_frame,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes)
        heading = gui.Heading(
            settings_frame,
            text='Indicator colours:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.ui_instance.show_help('Indicator colours')
        #
        help_button = tkinter.Button(
            settings_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
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
        settings_frame.grid(row=0, column=1, **self.grid_fullwidth)
        self.__do_toggle_height()



class UserInterface:

    """GUI using tkinter (base class for pyxelate)"""

    phase_open_file = 'open_file'
    phase_select_area = 'select_area'
    phases = (phase_open_file, phase_select_area)

    action_class = InterfacePlugin
    callback_class = Callbacks
    panel_class = Panels
    rollback_class = InterfacePlugin

    canvas_width = 900
    canvas_height = 640

    script_name = '<module pyxelate.app>'
    version = '<version>'
    homepage = 'https://github.com/blackstream-x/pyxelate'
    copyright_notice = """Copyright (C) 2021 Rainer Schwarzbach

    This file is part of pyxelate.

    pyxelate is free software: you can redistribute it and/or modify
    it under the terms of the MIT License.

    pyxelate is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
    See the LICENSE file for more details."""

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

    def __init__(self,
                 file_path,
                 script_path,
                 window_title='Base UI'):
        """Build the GUI"""
        open_support, save_support = pixelations.get_supported_extensions()
        #logging.debug('File formats open support: %r', open_support)
        #logging.debug('File formats save support: %r', save_support)
        self.main_window = tkinter.Tk()
        self.main_window.title(f'pyxelate: {window_title}')
        self.vars = Namespace(
            open_support=sorted(open_support),
            save_support=sorted(save_support),
            current_panel=None,
            errors=[],
            tk_image=None,
            image=None,
            original_path=file_path,
            trace=False,
            unapplied_changes=False,
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
            buttonstate=Namespace(
                apply=tkinter.StringVar(),
                save=tkinter.StringVar()),
        )
        self.widgets = Namespace(
            action_area=None,
            # buttons_area=None,
            buttons=Namespace(
                undo=None,
                apply=None,
                save=None),
            canvas=None,
            height=None)
        self.actions = self.action_class(self)
        self.callbacks = self.callback_class(self)
        self.panels = self.panel_class(self)
        self.rollbacks = self.rollback_class(self)
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
        self.do_open_file(
            keep_existing=True,
            quit_on_empty_choice=True)
        self.main_window.protocol('WM_DELETE_WINDOW', self.quit)
        self.main_window.mainloop()

    def do_open_file(self,
                     keep_existing=False,
                     preset_path=None,
                     quit_on_empty_choice=False):
        """Open a file via file dialog"""
        self.vars.current_panel = self.phase_open_file
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
            # if the selected file is not an image
            if self.vars.open_support and \
                    file_path.suffix not in self.vars.open_support:
                messagebox.showerror(
                    'Unsupported file type',
                    f'{file_path.name!r} is not a supported image file.',
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
                self.do_load_image(file_path)
            except OSError as error:
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

    def do_draw_indicator(self, stipple=None):
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
            INDICATOR, "<ButtonPress-1>",
            self.callbacks.indicator_drag_start)
        canvas.tag_bind(
            INDICATOR, "<ButtonRelease-1>",
            self.callbacks.indicator_drag_stop)
        canvas.tag_bind(
            INDICATOR, "<B1-Motion>",
            self.callbacks.indicator_drag_move)

    def do_load_image(self, file_path):
        """Load the image"""
        self.vars.image = pixelations.ImagePixelation(
            file_path,
            canvas_size=(self.canvas_width, self.canvas_height))
        # set selection sizes and reduce them
        # to the image dimensions if necessary
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
        self.do_update_selection(
            center_x=im_width // 2,
            center_y=im_height // 2,
            width=min(sel_width, im_width),
            height=min(sel_height, im_height))
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
        # set the original path and displayed file name
        self.vars.original_path = file_path
        self.tkvars.file_name.set(file_path.name)
        self.vars.unapplied_changes = False

    def do_pixelate(self):
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
        self.do_show_image()

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

    def do_show_image(self):
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

    def do_toggle_height(self):
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
            self.do_update_button('undo', tkinter.DISABLED)
        #
        (previous_image, previous_selection, unapplied_changes) = last_state
        self.vars.image.set_original(previous_image)
        self.vars.trace = False
        previous_selection.restore_to(self.tkvars.selection)
        self.vars.trace = True
        self.do_pixelate()
        self.do_draw_indicator(stipple='error')
        self.main_window.update_idletasks()
        time.sleep(.2)
        self.do_draw_indicator()
        self.vars.unapplied_changes = unapplied_changes
        self.tkvars.buttonstate.apply.set(tkinter.NORMAL)

    def do_update_button(self, button_name, new_state):
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

    def do_update_selection(self, **kwargs):
        """Update the selection for the provided key=value pairs"""
        self.vars.trace = False
        for (key, value) in kwargs.items():
            self.tkvars.selection[key].set(value)
        #
        self.vars.trace = True

    def __next_action(self):
        """Execute the next action"""
        current_index = self.phases.index(self.vars.current_panel)
        next_index = current_index + 1
        try:
            next_phase = self.phases[next_index]
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

    def panel_select_area(self):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        self.__show_settings_frame()
        image_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=self.canvas_width,
            height=self.canvas_height)
        self.vars.tk_image = self.vars.image.tk_original
        self.widgets.canvas.create_image(
            0, 0,
            image=self.vars.tk_image,
            anchor=tkinter.NW,
            tags='image')
        self.widgets.canvas.grid()
        self.do_draw_indicator()
        self.do_pixelate()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.tag_bind(
            'image', "<ButtonPress-1>", self.callbacks.selection_drag_start)
        self.widgets.canvas.tag_bind(
            'image', "<ButtonRelease-1>", self.callbacks.selection_drag_stop)
        self.widgets.canvas.tag_bind(
            'image', "<B1-Motion>", self.callbacks.selection_drag_move)
        image_frame.grid(row=0, column=0, rowspan=3, **self.grid_fullwidth)

    def previous_panel(self):
        """Go to the next panel"""
        phase_name = self.vars.current_panel
        phase_index = self.phases.index(phase_name)
        method_display = (
            f'Rollback method for phase #{phase_index} ({phase_name})')
        method_name = f'rollback_{phase_name}'
        try:
            rollback_method = getattr(self, method_name)
        except AttributeError:
            logging.warning('%s is undefined', method_display)
        else:
            self.vars.current_phase = self.phases[phase_index - 1]
            try:
                rollback_method()
            except NotImplementedError:
                self.vars.errors.append(
                    f'{method_display} has not been implemented yet')
            #
        #
        self.__show_panel()

    def pre_quit_check(self):
        """Pre-quit checks eg. for files to save.
        If this method of an inherited class returns False,
        the application will NOT exit,
        """
        raise NotImplementedError

    def quit(self, event=None):
        """Exit the application"""
        del event
        if self.pre_quit_check():
            self.main_window.destroy()
        #

    def __show_about(self):
        """Show information about the application
        in a modal dialog
        """
        gui.InfoDialog(
            self.main_window,
            (self.script_name,
             f'Version: {self.version}\nProject homepage: {self.homepage}'),
            ('Copyright/License:', self.copyright_notice),
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
        try:
            info_sequence = list(self.vars.help[topic].items())
        except AttributeError:
            # Not a hash -> generate a heading
            info_sequence = [(f'{topic} help:', self.vars.help[topic])]
        except KeyError:
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
        self.widgets.action_area.grid(**self.grid_fullwidth)
        #
        buttons_area = tkinter.Frame(self.widgets.action_area)
        buttons_grid = dict(padx=5, pady=5, sticky=tkinter.E)
        #
        last_row = self.show_additional_buttons(buttons_area, buttons_grid)
        help_button = tkinter.Button(
            buttons_area,
            text='\u2753 Help',
            command=self.__show_help)
        help_button.grid(row=last_row, column=0, **buttons_grid)
        about_button = tkinter.Button(
            buttons_area,
            text='\u24d8 About',
            command=self.__show_about)
        about_button.grid(row=last_row, column=1, **buttons_grid)
        quit_button = tkinter.Button(
            buttons_area,
            text='\u23fb Quit',
            command=self.quit)
        quit_button.grid(row=last_row, column=2, **buttons_grid)
        self.widgets.action_area.rowconfigure(1, weight=100)
        buttons_area.grid(row=2, column=1, sticky=tkinter.E)

    def show_additional_buttons(self, buttons_area, buttons_grid):
        """Additional buttons for the pixelate_image script.
        Return the number of rows (= the row index for th last row)
        """
        del buttons_area
        del buttons_grid
        return 0

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
            command=self.do_show_image,
            text='active',
            variable=self.tkvars.show_preview,
            indicatoron=1)
        label.grid(sticky=tkinter.W, column=0)
        preview_active.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label), column=1, columnspan=3)

    def __show_settings_frame(self,
                              fixed_tilesize=False,
                              allowed_shapes=ALL_SHAPES):
        """Show the settings frame"""
        settings_frame = tkinter.Frame(
            self.widgets.action_area,
            **self.with_border)
        heading = gui.Heading(
            settings_frame,
            text='Original file:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.__show_help('Original file')
        #
        help_button = tkinter.Button(
            settings_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
        label = tkinter.Label(
            settings_frame,
            textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            settings_frame,
            text='Choose another file',
            command=self.do_open_file)
        choose_button.grid(sticky=tkinter.W, columnspan=4)
        heading = gui.Heading(
            settings_frame,
            text='Display:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.__show_help('Display')
        #
        help_button = tkinter.Button(
            settings_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
        if self.vars.image.display_ratio > 1:
            scale_factor = 'Size: scaled down (factor: %r)' % float(
                self.vars.image.display_ratio)
        else:
            scale_factor = 'Size: original dimensions'
        #
        label = tkinter.Label(settings_frame, text=scale_factor)
        label.grid(sticky=tkinter.W, columnspan=4)
        self.__show_shape_settings(
            settings_frame,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes)
        heading = gui.Heading(
            settings_frame,
            text='Indicator colours:',
            sticky=tkinter.W,
            columnspan=4)

        # TODO
        def show_help(self=self):
            return self.__show_help('Indicator colours')
        #
        help_button = tkinter.Button(
            settings_frame,
            text='\u2753',
            command=show_help)
        help_button.grid(
            row=gui.grid_row_of(heading), column=5, sticky=tkinter.E)
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
        settings_frame.grid(row=0, column=1, **self.grid_fullwidth)
        self.do_toggle_height()


#
# Functions
#



# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
