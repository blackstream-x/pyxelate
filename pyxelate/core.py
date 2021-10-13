# -*- coding: utf-8 -*-

"""

core.py

Core application parts of the pyxelate scripts

"""


import json
import logging
import os
import pathlib
import tkinter

from tkinter import filedialog
from tkinter import messagebox

# local modules

from pyxelate import gui


#
# Constants
#


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

ELLIPSE = "ellipse"
RECTANGLE = "rectangle"

OVAL = "\u2b2d ellipse"
CIRCLE = "\u25cb circle"
RECT = "\u25ad rectangle"
SQUARE = "\u25a1 square"

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
    "white",
    "black",
    "red",
    "green",
    "blue",
    "cyan",
    "yellow",
    "magenta",
)

# Items drawn on the canvas
INDICATOR = "indicator"
RUBBERBAND = "rubberband"

# Mouse drag actions (“Drag with the mouse on the canvas to …”)
MOVE_SELECTION = "move the selection"
RESIZE_SELECTION = "resize the selection"
NEW_SELECTION = "create a new selection"
MOVE_CROP_AREA = "move the crop area"
RESIZE_CROP_AREA = "resize the crop area"
NEW_CROP_AREA = "select the crop area"
PAN_ZOOMED_IMAGE = "pan the (zoomed) image"

MOUSE_DRAG_ACTIONS = (
    # Contains all implemented drag actions
    MOVE_SELECTION,
    RESIZE_SELECTION,
    NEW_SELECTION,
    NEW_CROP_AREA,
)

# Grid parameters
WITH_BORDER = dict(borderwidth=2, padx=5, pady=5, relief=tkinter.GROOVE)
GRID_FULLWIDTH = dict(padx=4, pady=2, sticky=tkinter.E + tkinter.W)


#
# Classes
#


class Namespace(dict):

    # pylint: disable=too-many-instance-attributes

    """A dict subclass that exposes its items as attributes.

    Warning: Namespace instances only have direct access to the
    attributes defined in the visible_attributes tuple
    """

    visible_attributes = ("items", "update")

    def __repr__(self):
        """Object representation"""
        return "{0}({1})".format(type(self).__name__, super().__repr__())

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
                "{0!r} object has no attribute {1!r}".format(
                    type(self).__name__, name
                )
            ) from error
        #

    def __setattr__(self, name, value):
        """Set an attribute"""
        self[name] = value

    def __delattr__(self, name):
        """Delete an attribute"""
        del self[name]

    def update(self, other):
        """Delete an attribute"""
        for key, value in other.items():
            self[key] = value
        #


class FrozenSelection:

    """Store a selection state"""

    variables = (
        "center_x",
        "center_y",
        "width",
        "height",
        "shape",
        "tilesize",
    )

    def __init__(self, selection):
        """Initialize values from the variables in the
        provided selection Namespace of tkinter variables
        """
        self.original_values = {
            key: selection[key].get() for key in self.variables
        }
        self.effective_values = dict(self.original_values)
        if self.effective_values["shape"] in QUADRATIC_SHAPES:
            self.effective_values["height"] = self.effective_values["width"]
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

    def __str__(
        self,
    ):
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

    drag_registry = {
        MOVE_SELECTION: "move_sel",
        RESIZE_SELECTION: "resize_sel",
        NEW_SELECTION: "new_sel",
        NEW_CROP_AREA: "new_crop",
    }

    def __clicked_inside_indicator(self, event):
        """Return True if the click was inside the indicator"""
        try:
            (left, top, right, bottom) = self.widgets.canvas.bbox(INDICATOR)
        except TypeError as error:
            logging.debug(error)
            return False
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
            if (relative_x ** 2 / semi_x ** 2) + (
                relative_y ** 2 / semi_y ** 2
            ) <= 1:
                return True
            #
        #
        return False

    def __get_translated_bbox(self, tag_name):
        """Get the bbox coordinates
        calculated from display to image size.
        Return a tuple of (left, top, right, bottom).
        """
        (left, top, right, bottom) = self.widgets.canvas.bbox(tag_name)
        return (
            self.vars.image.from_display_size(left),
            self.vars.image.from_display_size(top),
            self.vars.image.from_display_size(right),
            self.vars.image.from_display_size(bottom),
        )

    def __get_selection_coordinates(self, tag_name):
        """Get the bbox selection as a Namespace with the
        selection coordinates (center and dimensions),
        calculated from display to image size.
        Return a tuple of (width, height, center_x, center_y)
        """
        (left, top, right, bottom) = self.__get_translated_bbox(tag_name)
        width = right - left
        height = bottom - top
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        return (width, height, center_x, center_y)

    def get_traced_intvar(self, method_name, value=None):
        """Return a traced IntVar() calling
        this intance's method methodname
        """
        return gui.traced_variable(
            getattr(self, method_name), constructor=tkinter.IntVar, value=value
        )

    def get_traced_stringvar(self, method_name, value=None):
        """Return a traced IntVar() calling
        this intance's method methodname
        """
        return gui.traced_variable(getattr(self, method_name), value=value)

    def __execute_drag_method(self, event_type, event):
        """Execute the method for the specified event type,
        reading the drag_action variable
        """
        prefix = self.drag_registry[self.tkvars.drag_action.get()]
        method = getattr(self, "%s_drag_%s" % (prefix, event_type))
        return method(event)

    def next_drag_action(self, *unused_arguments):
        """Select the next drag action"""
        current_drag_action = self.tkvars.drag_action.get()
        current_index = MOUSE_DRAG_ACTIONS.index(current_drag_action)
        if current_index < len(MOUSE_DRAG_ACTIONS) - 1:
            self.tkvars.drag_action.set(MOUSE_DRAG_ACTIONS[current_index + 1])
        #

    def previous_drag_action(self, *unused_arguments):
        """Select the previous drag action"""
        current_drag_action = self.tkvars.drag_action.get()
        current_index = MOUSE_DRAG_ACTIONS.index(current_drag_action)
        if current_index:
            self.tkvars.drag_action.set(MOUSE_DRAG_ACTIONS[current_index - 1])
        #

    def drag_move(self, event):
        """Handle dragging"""
        return self.__execute_drag_method("move", event)

    def drag_start(self, event):
        """Begin drag"""
        return self.__execute_drag_method("start", event)

    def drag_stop(self, event):
        """End drag"""
        return self.__execute_drag_method("stop", event)

    def move_sel_drag_move(self, event):
        """Handle dragging of the indicator"""
        if self.vars.drag_data.item != INDICATOR:
            return False
        #
        # compute how much the mouse has moved
        current_x = event.x
        current_y = event.y
        delta_x = current_x - self.vars.drag_data.x
        delta_y = current_y - self.vars.drag_data.y
        # move the object the appropriate amount
        self.widgets.canvas.move(self.vars.drag_data.item, delta_x, delta_y)
        # record the new position
        self.vars.drag_data.x = current_x
        self.vars.drag_data.y = current_y
        # Update the selection (position only)
        (center_x, center_y) = self.__get_selection_coordinates(INDICATOR)[-2:]
        self.ui_instance.update_selection(center_x=center_x, center_y=center_y)
        self.ui_instance.pixelate_selection()
        return True

    def move_sel_drag_start(self, event):
        """Begin drag of the indicator"""
        if not self.__clicked_inside_indicator(event):
            return False
        #
        # record the item and its location
        self.vars.drag_data.item = INDICATOR
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def move_sel_drag_stop(self, *unused_event):
        """End drag of an object"""
        if self.vars.drag_data.item != INDICATOR:
            return False
        #
        # reset the drag information
        self.vars.drag_data.item = None
        self.vars.drag_data.x = 0
        self.vars.drag_data.y = 0
        # Trigger the selection change explicitly
        self.update_selection()
        return True

    def new_sel_drag_move(self, event):
        """Drag a new selection"""
        return self.__new_selection_drag_move(
            event.x, event.y, self.vars.drag_data.x, self.vars.drag_data.y
        )

    def new_sel_drag_start(self, event):
        """Begin dragging for a new selection"""
        # record the item and its location
        self.vars.drag_data.item = RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def new_sel_drag_stop(self, *unused_event):
        """End drag for a new selection"""
        try:
            (
                width,
                height,
                center_x,
                center_y,
            ) = self.__get_selection_coordinates(RUBBERBAND)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(RUBBERBAND)
        # Adjust to minimum sizes
        if width < MINIMUM_SELECTION_SIZE:
            width = MINIMUM_SELECTION_SIZE
        #
        if height < MINIMUM_SELECTION_SIZE:
            height = MINIMUM_SELECTION_SIZE
        #
        # Set the selection attributes
        self.ui_instance.update_selection(
            center_x=center_x, center_y=center_y, width=width, height=height
        )
        # Trigger the selection change explicitly
        self.update_selection()
        return True

    def new_crop_drag_move(self, event):
        """Drag a new crop area"""
        [left, right] = sorted((event.x, self.vars.drag_data.x))
        [top, bottom] = sorted((event.y, self.vars.drag_data.y))
        self.widgets.canvas.delete(RUBBERBAND)
        current_color = self.tkvars.indicator.drag_color.get()
        self.widgets.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline=current_color,
            tags=RUBBERBAND,
        )
        return True

    def new_crop_drag_start(self, event):
        """Begin dragging for a new crop area"""
        self.vars.drag_data.item = RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        return True

    def new_crop_drag_stop(self, *unused_event):
        """End drag for a new crop area"""
        try:
            (left, top, right, bottom) = self.__get_translated_bbox(RUBBERBAND)
        except TypeError:
            # No selection dragged (i.e. click without dragging)
            return False
        #
        self.widgets.canvas.delete(RUBBERBAND)
        # previous_crop_area = self.vars.crop_area
        self.vars.crop_area.update(
            dict(left=left, top=top, right=right, bottom=bottom)
        )
        # Switch the "crop" checkbox to "on",
        # triggering  the toggle_crop_display method implicitly
        # TODO: error handling
        self.tkvars.crop.set(1)
        return True

    def resize_sel_drag_move(self, event):
        """Drag for selection resize"""
        delta_x = event.x - self.vars.drag_data.x
        delta_y = event.y - self.vars.drag_data.y
        current_x = self.vars.drag_data.var_x + delta_x
        current_y = self.vars.drag_data.var_y + delta_y
        return self.__new_selection_drag_move(
            current_x,
            current_y,
            self.vars.drag_data.anchor_x,
            self.vars.drag_data.anchor_y,
        )

    def resize_sel_drag_start(self, event):
        """Begin dragging for selection resize"""
        # record the item and its location
        self.vars.drag_data.item = RUBBERBAND
        self.vars.drag_data.x = event.x
        self.vars.drag_data.y = event.y
        (left, top, right, bottom) = self.widgets.canvas.bbox(INDICATOR)
        center_x = (left + right) // 2
        center_y = (top + bottom) // 2
        # Ancor at the opposite side, seen from the selection center
        if event.x > center_x:
            self.vars.drag_data.anchor_x = left
            self.vars.drag_data.var_x = right
        else:
            self.vars.drag_data.var_x = left
            self.vars.drag_data.anchor_x = right
        #
        if event.y > center_y:
            self.vars.drag_data.anchor_y = top
            self.vars.drag_data.var_y = bottom
        else:
            self.vars.drag_data.var_y = top
            self.vars.drag_data.anchor_y = bottom
        #
        return True

    resize_sel_drag_stop = new_sel_drag_stop

    def __new_selection_drag_move(
        self, current_x, current_y, origin_x, origin_y
    ):
        """Move "rubber frame" of a new or resized selection"""
        [left, right] = sorted((current_x, origin_x))
        [top, bottom] = sorted((current_y, origin_y))
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
        self.widgets.canvas.delete(RUBBERBAND)
        outer_dash = (1, 1)
        shape = self.tkvars.selection.shape.get()
        current_color = self.tkvars.indicator.drag_color.get()
        if shape in ELLIPTIC_SHAPES:
            outer_dash = (5, 5)
        #
        self.widgets.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            dash=outer_dash,
            outline=current_color,
            tags=RUBBERBAND,
        )
        if shape in ELLIPTIC_SHAPES:
            self.widgets.canvas.create_oval(
                left,
                top,
                right,
                bottom,
                dash=(1, 1),
                outline=current_color,
                tags=RUBBERBAND,
            )
        # Update the selection
        (width, height, center_x, center_y) = self.__get_selection_coordinates(
            RUBBERBAND
        )
        self.ui_instance.update_selection(
            center_x=center_x, center_y=center_y, width=width, height=height
        )
        return True

    def redraw_indicator(self, *unused_arguments):
        """Trigger redrawing of the indicator"""
        try:
            self.ui_instance.draw_indicator()
        except AttributeError as error:
            logging.warning("%s", error)
        #

    def reset_crop_area(self):
        """Reset the crop area to the full image
        and set the crop checkbox to "off"
        """
        try:
            (width, height) = self.vars.image.size
        except AttributeError as error:
            logging.error("Could not reset the crop area: %s", error)
        else:
            self.vars.crop_area.update(
                dict(left=0, top=0, right=width, bottom=height)
            )
        #
        self.tkvars.crop.set(0)

    def toggle_crop_display(self, *unused_arguments):
        """Toggle crop area preview update"""
        if not self.vars.trace:
            return
        #
        if self.tkvars.crop.get():
            self.vars.image.set_crop_area(self.vars.crop_area)
        else:
            self.vars.image.remove_crop_area()
        #
        self.toggle_preview()

    def toggle_preview(self, *unused_arguments):
        """Trigger preview update"""
        try:
            self.ui_instance.show_image()
        except AttributeError as error:
            logging.warning("%s", error)
        #

    def update_buttons(self, *unused_arguments):
        """Trigger button state updates in subclasses"""
        raise NotImplementedError

    def update_selection(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.ui_instance.pixelate_selection()
            self.ui_instance.draw_indicator()
        #
        self.ui_instance.toggle_height()


class Panels(InterfacePlugin):

    """Panel and panel component methods"""

    # pylint: disable=too-many-locals
    def component_shape_settings(
        self, settings_frame, fixed_tilesize=False, allowed_shapes=ALL_SHAPES
    ):
        """Show the shape part of the settings frame"""
        self.ui_instance.heading_with_help_button(settings_frame, "Selection")
        label = tkinter.Label(settings_frame, text="Tile size:")
        if fixed_tilesize:
            ts_state = tkinter.DISABLED
        else:
            ts_state = "readonly"
        #
        tilesize = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_TILESIZE,
            to=MAXIMUM_TILESIZE,
            increment=TILESIZE_INCREMENT,
            justify=tkinter.RIGHT,
            state=ts_state,
            width=4,
            textvariable=self.tkvars.selection.tilesize,
        )
        #
        label.grid(sticky=tkinter.W, column=0)
        tilesize.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Shape:")
        shape_opts = tkinter.OptionMenu(
            settings_frame, self.tkvars.selection.shape, *allowed_shapes
        )
        label.grid(sticky=tkinter.W, column=0)
        shape_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Width:")
        width = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.width,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.selection.width,
        )
        label.grid(sticky=tkinter.W, column=0)
        width.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Height:")
        self.widgets.height = tkinter.Spinbox(
            settings_frame,
            from_=MINIMUM_SELECTION_SIZE,
            to=self.vars.image.original.height,
            justify=tkinter.RIGHT,
            state="readonly",
            width=4,
            textvariable=self.tkvars.selection.height,
        )
        label.grid(sticky=tkinter.W, column=0)
        self.widgets.height.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="Center at x:")
        center_x = tkinter.Spinbox(
            settings_frame,
            from_=-self.vars.image.original.width,
            to=2 * self.vars.image.original.width,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_x,
        )
        label_sep = tkinter.Label(settings_frame, text=", y:")
        center_y = tkinter.Spinbox(
            settings_frame,
            from_=-self.vars.image.original.height,
            to=2 * self.vars.image.original.height,
            justify=tkinter.RIGHT,
            width=4,
            textvariable=self.tkvars.selection.center_y,
        )
        label.grid(sticky=tkinter.W, column=0)
        center_x.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=1)
        label_sep.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=2)
        center_y.grid(sticky=tkinter.W, row=gui.grid_row_of(label), column=3)
        label = tkinter.Label(settings_frame, text="Preview:")
        preview_active = tkinter.Checkbutton(
            settings_frame,
            command=self.ui_instance.show_image,
            text="active",
            variable=self.tkvars.show_preview,
            indicatoron=1,
        )
        label.grid(sticky=tkinter.W, column=0)
        preview_active.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )

    def component_file_info(self, parent_frame):
        """Show information about the current file"""
        self.ui_instance.heading_with_help_button(
            parent_frame, "Original file"
        )
        label = tkinter.Label(parent_frame, textvariable=self.tkvars.file_name)
        label.grid(sticky=tkinter.W, columnspan=5)
        choose_button = tkinter.Button(
            parent_frame,
            text="Choose another file",
            command=self.ui_instance.open_file,
        )
        choose_button.grid(sticky=tkinter.W, columnspan=4)

    def component_image_info(
        self, parent_frame, frame_position, change_enabled=False
    ):
        """Show information about the current image"""
        raise NotImplementedError

    def component_select_area(
        self,
        frame_position=None,
        change_enabled=False,
        fixed_tilesize=False,
        allowed_shapes=ALL_SHAPES,
    ):
        """Show the image on a canvas and let
        the user select the area to be pixelated
        """
        image_frame = tkinter.Frame(self.widgets.action_area, **WITH_BORDER)
        self.widgets.canvas = tkinter.Canvas(
            image_frame,
            width=self.vars.canvas_width,
            height=self.vars.canvas_height,
        )
        self.vars.tk_image = self.vars.image.tk_original
        self.widgets.canvas.create_image(
            0, 0, image=self.vars.tk_image, anchor=tkinter.NW, tags="image"
        )
        self.widgets.canvas.grid()
        self.ui_instance.draw_indicator()
        self.ui_instance.pixelate_selection()
        self.vars.trace = True
        # add bindings to create a new selector
        self.widgets.canvas.bind(
            "<ButtonPress-1>", self.ui_instance.callbacks.drag_start
        )
        self.widgets.canvas.bind(
            "<ButtonRelease-1>", self.ui_instance.callbacks.drag_stop
        )
        self.widgets.canvas.bind(
            "<B1-Motion>", self.ui_instance.callbacks.drag_move
        )
        image_frame.grid(row=1, column=0, rowspan=3, **GRID_FULLWIDTH)
        self.sidebar_settings(
            frame_position,
            change_enabled=change_enabled,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes,
        )

    def sidebar_settings(
        self,
        frame_position,
        change_enabled=False,
        fixed_tilesize=False,
        allowed_shapes=ALL_SHAPES,
    ):
        """Show the settings sidebar"""
        settings_frame = tkinter.Frame(self.widgets.action_area, **WITH_BORDER)
        self.component_file_info(settings_frame)
        self.component_image_info(
            settings_frame, frame_position, change_enabled=change_enabled
        )
        self.component_shape_settings(
            settings_frame,
            fixed_tilesize=fixed_tilesize,
            allowed_shapes=allowed_shapes,
        )
        self.ui_instance.heading_with_help_button(
            settings_frame, "Indicator colours"
        )
        label = tkinter.Label(settings_frame, text="Current:")
        color_opts = tkinter.OptionMenu(
            settings_frame,
            self.tkvars.indicator.color,
            *POSSIBLE_INDICATOR_COLORS,
        )
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        label = tkinter.Label(settings_frame, text="New:")
        color_opts = tkinter.OptionMenu(
            settings_frame,
            self.tkvars.indicator.drag_color,
            *POSSIBLE_INDICATOR_COLORS,
        )
        label.grid(sticky=tkinter.W, column=0)
        color_opts.grid(
            sticky=tkinter.W,
            row=gui.grid_row_of(label),
            column=1,
            columnspan=3,
        )
        self.ui_instance.heading_with_help_button(
            settings_frame, "Drag on the canvas to"
        )
        drag_opts = tkinter.OptionMenu(
            settings_frame, self.tkvars.drag_action, *MOUSE_DRAG_ACTIONS
        )
        drag_opts.grid(sticky=tkinter.W, column=0, columnspan=4)
        settings_frame.columnconfigure(4, weight=100)
        settings_frame.grid(row=0, column=1, rowspan=2, **GRID_FULLWIDTH)
        self.ui_instance.toggle_height()


class UserInterface:

    """GUI using tkinter (base class for pyxelate)"""

    phase_open_file = "open_file"
    phase_select_area = "select_area"
    phases = (phase_open_file, phase_select_area)
    panel_names = {
        phase_open_file: "Open file",
        phase_select_area: "Select area …",
    }

    action_class = InterfacePlugin
    callback_class = Callbacks
    panel_class = Panels
    rollback_class = InterfacePlugin

    script_name = "<module pyxelate.app>"
    version = "<version>"
    homepage = "https://github.com/blackstream-x/pyxelate"
    copyright_notice = COPYRIGHT_NOTICE

    file_type = "image file"

    # pylint: disable=attribute-defined-outside-init

    def __init__(
        self,
        file_path,
        options,
        script_path,
        canvas_width=900,
        canvas_height=640,
    ):
        """Build the GUI"""
        self.options = options
        self.main_window = tkinter.Tk()
        self.main_window.title(f"pyxelate: {self.script_name}")
        self.vars = Namespace(
            current_panel=None,
            errors=[],
            canvas_width=canvas_width,
            canvas_height=canvas_height,
            tk_image=None,
            image=None,
            original_path=file_path,
            trace=False,
            unapplied_changes=False,
            undo_buffer=[],
            drag_data=Namespace(
                x=0, y=0, anchor_x=0, anchor_y=0, var_x=0, var_y=0, item=None
            ),
            crop_area=Namespace(left=0, top=0, right=0, bottom=0),
        )
        self.tkvars = Namespace(
            file_name=tkinter.StringVar(),
            drag_action=tkinter.StringVar(),
            show_preview=tkinter.IntVar(),
        )
        self.tkvars.drag_action.set(MOVE_SELECTION)
        self.widgets = Namespace(
            action_area=None,
            # buttons_area=None,
            canvas=None,
            height=None,
        )
        self.actions = self.action_class(self)
        self.callbacks = self.callback_class(self)
        self.panels = self.panel_class(self)
        self.rollbacks = self.rollback_class(self)
        self.additional_variables()
        self.additional_widgets()
        #
        # Load help file
        with open(
            script_path.parent / "docs" / f"{script_path.stem}_help.json"
        ) as help_file:
            self.vars.help = json.load(help_file)
        #
        self.open_file(keep_existing=True, quit_on_empty_choice=True)
        self.main_window.protocol("WM_DELETE_WINDOW", self.quit)
        self.main_window.mainloop()

    def additional_variables(self):
        """Subclass-specific post-initialization
        (additional variables)
        """
        self.tkvars.update(
            dict(
                # Update the selection
                # after change of any of the following parameters
                selection=Namespace(
                    center_x=self.callbacks.get_traced_intvar(
                        "update_selection"
                    ),
                    center_y=self.callbacks.get_traced_intvar(
                        "update_selection"
                    ),
                    width=self.callbacks.get_traced_intvar("update_selection"),
                    height=self.callbacks.get_traced_intvar(
                        "update_selection"
                    ),
                    shape=self.callbacks.get_traced_stringvar(
                        "update_selection"
                    ),
                    tilesize=self.callbacks.get_traced_intvar(
                        "update_selection"
                    ),
                ),
                # Redraw the indicator
                # each time the outline color is changed
                indicator=Namespace(
                    color=self.callbacks.get_traced_stringvar(
                        "redraw_indicator", value="red"
                    ),
                    drag_color=tkinter.StringVar(),
                ),
                crop=self.callbacks.get_traced_intvar(
                    "toggle_crop_display", value=0
                ),
            )
        )
        #
        self.tkvars.indicator.drag_color.set("blue")

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        raise NotImplementedError

    def open_file(
        self, keep_existing=False, preset_path=None, quit_on_empty_choice=False
    ):
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
                    title=f"Load a {self.file_type}",
                )
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
            if not self.check_file_type(file_path):
                messagebox.showerror(
                    "Unsupported file type",
                    f"{file_path.name!r} is not a supported file.",
                    icon=messagebox.ERROR,
                )
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            if self.vars.unapplied_changes or self.vars.undo_buffer:
                confirmation = messagebox.askokcancel(
                    "Unsaved Changes",
                    "Discard the chages made to"
                    f" {self.vars.original_path.name!r}?",
                    icon=messagebox.WARNING,
                )
                if not confirmation:
                    return
                #
            #
            # Set original_path and read image data
            try:
                self.load_file(file_path)
            except (OSError, ValueError) as error:
                messagebox.showerror(
                    "Load error", str(error), icon=messagebox.ERROR
                )
                initial_dir = str(file_path.parent)
                file_path = None
                continue
            #
            break
        #
        self.vars.undo_buffer.clear()
        self.next_panel()

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        raise NotImplementedError

    def heading_with_help_button(
        self, parent_frame, subject, heading_column_span=4
    ):
        """A heading with an adjacent help button"""
        heading = gui.Heading(
            parent_frame,
            text=f"{subject}:",
            sticky=tkinter.W,
            columnspan=heading_column_span,
        )

        # Inner function for the "extra arguments" trick, see
        # <https://tkdocs.com/shipman/extra-args.html>
        def show_help(self=self):
            return self.show_help(topic=subject)

        #
        help_button = tkinter.Button(
            parent_frame,
            # text='\u2753',
            text="?",
            command=show_help,
        )
        help_button.grid(
            row=gui.grid_row_of(heading),
            column=heading_column_span,
            sticky=tkinter.E,
        )

    def load_file(self, file_path):
        """Load the file"""
        raise NotImplementedError

    def draw_indicator(self, stipple=None):
        """Draw the pixelation selector on the canvas,
        its coordinates determined by the px_* variables
        """
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        width = self.vars.image.to_display_size(
            self.tkvars.selection.width.get()
        )
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.vars.image.to_display_size(
                self.tkvars.selection.height.get()
            )
        #
        center_x = self.vars.image.to_display_size(
            self.tkvars.selection.center_x.get()
        )
        center_y = self.vars.image.to_display_size(
            self.tkvars.selection.center_y.get()
        )
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
            tags=INDICATOR,
        )
        if stipple:
            appearance.update(
                dict(width=1, fill=current_color, stipple=stipple)
            )
        #
        create_widget(left, top, right, bottom, **appearance)

    def pixelate_selection(self):
        """Apply the pixelation to the image and update the preview"""
        self.vars.image.set_tilesize(self.tkvars.selection.tilesize.get())
        width = self.tkvars.selection.width.get()
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            height = width
        else:
            height = self.tkvars.selection.height.get()
        #
        self.vars.image.set_shape(
            (
                self.tkvars.selection.center_x.get(),
                self.tkvars.selection.center_y.get(),
            ),
            SHAPES[self.tkvars.selection.shape.get()],
            (width, height),
        )
        self.show_image()

    def save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        raise NotImplementedError

    def show_image(self):
        """Show image or preview according to the show_preview setting"""
        canvas = self.widgets.canvas
        if not canvas:
            return
        #
        canvas.delete("image")
        if self.tkvars.show_preview.get():
            self.vars.tk_image = self.vars.image.get_tk_image(
                self.vars.image.result
            )
        else:
            self.vars.tk_image = self.vars.image.tk_original
        #
        canvas.create_image(
            0, 0, image=self.vars.tk_image, anchor=tkinter.NW, tags="image"
        )
        canvas.tag_lower("image", INDICATOR)

    def __next_action(self):
        """Execute the next action"""
        current_index = self.phases.index(self.vars.current_panel)
        next_index = current_index + 1
        try:
            next_phase = self.phases[next_index]
        except IndexError as error:
            raise ValueError(
                f"Phase number #{next_index} out of range"
            ) from error
        #
        method_display = (
            f"Action method for phase #{next_index} ({next_phase})"
        )
        try:
            action_method = getattr(self.actions, next_phase)
        except AttributeError:
            logging.debug("%s is undefined", method_display)
        else:
            try:
                action_method()
            except NotImplementedError as error:
                raise ValueError(
                    f"{method_display} has not been implemented yet"
                ) from error
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

    def previous_panel(self):
        """Go to the next panel"""
        phase_name = self.vars.current_panel
        phase_index = self.phases.index(phase_name)
        method_display = (
            f"Rollback method for phase #{phase_index} ({phase_name})"
        )
        try:
            rollback_method = getattr(self.rollbacks, phase_name)
        except AttributeError:
            logging.warning("%s is undefined", method_display)
        else:
            self.vars.current_phase = self.phases[phase_index - 1]
            try:
                rollback_method()
            except NotImplementedError:
                self.vars.errors.append(
                    f"{method_display} has not been implemented yet"
                )
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

    def show_additional_buttons(self, buttons_area, buttons_grid):
        """Additional buttons for the pixelate_image script.
        Return the number of rows (= the row index for th last row)
        """
        raise NotImplementedError

    def __show_about(self):
        """Show information about the application
        in a modal dialog
        """
        gui.InfoDialog(
            self.main_window,
            (
                self.script_name,
                f"Version: {self.version}\nProject homepage: {self.homepage}",
            ),
            ("Copyright/License:", self.copyright_notice),
            title="About…",
        )
        #

    def __show_errors(self):
        """Show errors if there are any"""
        if self.vars.errors:
            gui.InfoDialog(
                self.main_window,
                ("Errors:", "\n".join(self.vars.errors)),
                title="Errors occurred!",
            )
            self.vars.errors.clear()
        #

    def show_help(self, topic="Global"):
        """Show help for the provided topic"""
        try:
            info_sequence = list(self.vars.help[topic].items())
        except AttributeError:
            # Not a hash -> generate a heading
            info_sequence = [(f"{topic} help:", self.vars.help[topic])]
        except KeyError:
            info_sequence = [("Error:", f"No help for {topic} available yet")]
        #
        gui.InfoDialog(
            self.main_window, *info_sequence, title=f"Help ({topic})"
        )

    def __show_panel(self):
        """Show a panel.
        Add the "Previous", "Next", "Choose another relase",
        "About" and "Quit" buttons at the bottom
        """
        try:
            self.widgets.action_area.destroy()
        except AttributeError:
            pass
        #
        self.widgets.action_area = tkinter.Frame(self.main_window)
        try:
            panel_method = getattr(self.panels, self.vars.current_phase)
        except AttributeError:
            self.vars.errors.append(
                "Panel for Phase %r has not been implemented yet,"
                " going back to phase %r."
                % (self.vars.current_phase, self.vars.current_panel)
            )
            self.vars.current_phase = self.vars.current_panel
            panel_method = getattr(self.panels, self.vars.current_phase)
        else:
            self.vars.current_panel = self.vars.current_phase
        #
        self.__show_errors()
        logging.debug("Showing panel %r", self.vars.current_panel)
        gui.Heading(
            self.widgets.action_area,
            text=self.panel_names[self.vars.current_panel],
            row=0,
            column=0,
            # **GRID_FULLWIDTH,
            sticky=tkinter.E + tkinter.W,
            **WITH_BORDER,
        )
        panel_method()
        self.widgets.action_area.grid(**GRID_FULLWIDTH)
        #
        buttons_area = tkinter.Frame(self.widgets.action_area)
        buttons_grid = dict(padx=5, pady=5, sticky=tkinter.E)
        #
        last_row = self.show_additional_buttons(buttons_area, buttons_grid)
        help_button = tkinter.Button(
            buttons_area, text="\u2753 Help", command=self.show_help
        )
        help_button.grid(row=last_row, column=0, **buttons_grid)
        about_button = tkinter.Button(
            buttons_area, text="\u24d8 About", command=self.__show_about
        )
        about_button.grid(row=last_row, column=1, **buttons_grid)
        quit_button = tkinter.Button(
            buttons_area, text="\u23fb Quit", command=self.quit
        )
        quit_button.grid(row=last_row, column=2, **buttons_grid)
        self.widgets.action_area.rowconfigure(2, weight=100)
        buttons_area.grid(row=3, column=1, sticky=tkinter.E)
        self.main_window.bind_all(
            "<KeyPress-Prior>", self.callbacks.previous_drag_action
        )
        self.main_window.bind_all(
            "<KeyPress-Next>", self.callbacks.next_drag_action
        )

    def toggle_height(self):
        """Toggle height spinbox to follow width"""
        if self.tkvars.selection.shape.get() in QUADRATIC_SHAPES:
            gui.reconfigure_widget(
                self.widgets.height,
                state=tkinter.DISABLED,
                textvariable=self.tkvars.selection.width,
            )
        else:
            gui.reconfigure_widget(
                self.widgets.height,
                state="readonly",
                textvariable=self.tkvars.selection.height,
            )
        #

    def update_selection(self, **kwargs):
        """Update the selection for the provided key=value pairs"""
        self.vars.trace = False
        for (key, value) in kwargs.items():
            self.tkvars.selection[key].set(value)
        #
        self.vars.trace = True


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
