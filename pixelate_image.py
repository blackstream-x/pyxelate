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

from pyxelate import core
from pyxelate import gui
from pyxelate import pixelations


#
# Constants
#


SCRIPT_NAME = "Partially pixelate an image"
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

# Phases and panel names
OPEN_FILE = core.UserInterface.phase_open_file
SELECT_AREA = "select_area"

PHASES = (OPEN_FILE, SELECT_AREA)

PANEL_NAMES = {SELECT_AREA: "Select area to be pixelated"}


UNDO_SIZE = 20

CANVAS_WIDTH = 900
CANVAS_HEIGHT = 640


#
# Classes
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
        provided selection app.Namespace of tkinter variables
        """
        self.original_values = {
            key: selection[key].get() for key in self.variables
        }
        self.effective_values = dict(self.original_values)
        if self.effective_values["shape"] in core.QUADRATIC_SHAPES:
            self.effective_values["height"] = self.effective_values["width"]
        #

    def restore_to(self, px_image):
        """Restore values to the variables in the
        provided selection app.Namespace of tkinter variables
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


class ImageCallbacks(core.Callbacks):

    """Callbacks for the new user interface"""

    def toggle_crop_display(self, *unused_arguments):
        """Toggle crop area preview update
        and re-enable the "save" button
        """
        super().toggle_crop_display(*unused_arguments)
        self.tkvars.buttonstate.save.set(tkinter.NORMAL)

    def update_buttons(self, *unused_arguments):
        """Trigger undo, apply and save button states changes"""
        if self.vars.undo_buffer:
            desired_undo_state = tkinter.NORMAL
        else:
            desired_undo_state = tkinter.DISABLED
        #
        gui.set_state(self.widgets.buttons.undo, desired_undo_state)
        for button_name in ("apply", "save"):
            gui.set_state(
                self.widgets.buttons[button_name],
                self.tkvars.buttonstate[button_name].get(),
            )
        #

    def update_selection(self, *unused_arguments):
        """Trigger update after selection changed"""
        if self.vars.trace:
            self.vars.unapplied_changes = True
            self.tkvars.buttonstate.apply.set(tkinter.NORMAL)
            self.tkvars.buttonstate.save.set(tkinter.NORMAL)
        #
        super().update_selection()


class Panels(core.Panels):

    """Panels and panel components"""

    def component_image_info(self, parent_frame):
        """Show information about the image"""
        self.application.heading_with_help_button(parent_frame, "Image")
        #
        self.component_zoom_factor(parent_frame)
        crop_active = tkinter.Checkbutton(
            parent_frame,
            anchor=tkinter.W,
            text="Crop image",
            variable=self.tkvars.crop,
            indicatoron=1,
        )
        crop_active.grid(
            sticky=tkinter.W,
            column=0,
            columnspan=5,
        )

    def select_area(self):
        """Panel for the "Select area" phase"""
        self.component_image_on_canvas()
        self.sidebar_settings()


class ImageUI(core.UserInterface):

    """Modular user interface for image pixelation"""

    phases = PHASES
    panel_names = PANEL_NAMES
    script_name = SCRIPT_NAME
    version = VERSION
    copyright_notice = COPYRIGHT_NOTICE

    callback_class = ImageCallbacks
    panel_class = Panels

    def __init__(self, file_path, options):
        """Initialize super class"""
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
        open_support, save_support = pixelations.get_supported_extensions()
        logging.debug("File formats open support: %r", open_support)
        logging.debug("File formats save support: %r", save_support)
        self.vars.update(
            open_support=sorted(open_support),
            save_support=sorted(save_support),
        )
        self.tkvars.update(
            buttonstate=core.Namespace(
                apply=self.callbacks.get_traced_stringvar(
                    "update_buttons", value=tkinter.NORMAL
                ),
                save=self.callbacks.get_traced_stringvar(
                    "update_buttons", value=tkinter.NORMAL
                ),
            )
        )

    def additional_widgets(self):
        """Subclass-specific post-initialization
        (additional widgets)
        """
        self.widgets.update(
            buttons=core.Namespace(undo=None, apply=None, save=None)
        )

    def apply_pixelation(self):
        """Apply changes to the image"""
        # Append the current state to the undo buffer
        self.vars.undo_buffer.append(
            (
                self.vars.image.original,
                FrozenSelection(self.tkvars.selection),
                self.vars.unapplied_changes,
            )
        )
        if len(self.vars.undo_buffer) > UNDO_SIZE:
            del self.vars.undo_buffer[:-UNDO_SIZE]
        #
        # Visual feedback
        self.draw_indicator(stipple="gray75")
        self.main_window.update_idletasks()
        time.sleep(0.2)
        self.draw_indicator()
        self.vars.image.set_original(self.vars.image.result)
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.NORMAL)
        self.callbacks.toggle_preview()
        self.vars.unapplied_changes = False

    def check_file_type(self, file_path):
        """Return True if the file is a supported file,
        False if not
        """
        if (
            self.vars.open_support
            and file_path.suffix not in self.vars.open_support
        ):
            return False
        #
        return True

    def __get_save_recommendation(self, ask_to_apply=False):
        """Return True or False (depending on the necessity to
        save the image)
        """
        try:
            last_applied_selection = self.vars.undo_buffer[-1][1]
        except IndexError:
            logging.debug("No last applied selection!")
        else:
            current_selection = FrozenSelection(self.tkvars.selection)
            logging.debug("Last applied selection: %s", last_applied_selection)
            logging.debug("Current selection:      %s", current_selection)
            logging.debug(
                "Selections are equal: %r",
                current_selection == last_applied_selection,
            )
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
                "Not yet applied changes",
                "Pixelate the current selection before saving?",
                default=default_answer,
            ):
                self.apply_pixelation()
            #
        #
        return bool(self.vars.undo_buffer)

    def load_file(self, file_path):
        """Load the image"""
        self.vars.update(
            image=pixelations.ImagePixelation(
                file_path,
                canvas_size=(self.vars.canvas_width, self.vars.canvas_height),
            )
        )
        self.set_default_selection()
        # set the show_preview variable by default
        self.tkvars.show_preview.set(1)
        # set the original path and displayed file name
        self.vars.update(original_path=file_path, unapplied_changes=False)
        self.tkvars.file_name.set(file_path.name)
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.DISABLED)

    def pre_quit_check(self):
        """Check if there are unsaved changes
        before exiting the application
        """
        if self.__get_save_recommendation(ask_to_apply=False):
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
        return True

    def revert_last_pixelation(self):
        """Revert to the state before doing the last apply"""
        try:
            last_state = self.vars.undo_buffer.pop()
        except IndexError:
            return
        #
        if not self.vars.undo_buffer:
            gui.set_state(self.widgets.buttons.undo, tkinter.DISABLED)
        #
        (previous_image, previous_selection, unapplied_changes) = last_state
        self.vars.image.set_original(previous_image)
        self.vars.trace = False
        previous_selection.restore_to(self.tkvars.selection)
        self.vars.trace = True
        self.pixelate_selection()
        self.draw_indicator(stipple="error")
        self.main_window.update_idletasks()
        time.sleep(0.2)
        self.draw_indicator()
        self.vars.unapplied_changes = unapplied_changes
        self.tkvars.buttonstate.apply.set(tkinter.NORMAL)

    def save_file(self):
        """Save as the selected file,
        return True if the file was saved
        """
        if not self.__get_save_recommendation(ask_to_apply=True):
            messagebox.showinfo("Image unchanged", "Nothing to save.")
            return False
        #
        original_suffix = self.vars.original_path.suffix
        filetypes = [
            ("Supported image files", f"*{suffix}")
            for suffix in self.vars.save_support
        ] + [("All files", "*.*")]
        selected_file = filedialog.asksaveasfilename(
            initialdir=str(self.vars.original_path.parent),
            defaultextension=original_suffix,
            filetypes=filetypes,
            parent=self.main_window,
            title="Save pixelated image as…",
        )
        if not selected_file:
            return False
        #
        logging.debug("Saving the file as %r", selected_file)
        #  save the file and reset the "touched" flag
        self.vars.image.cropped_original.save(selected_file)
        self.vars.original_path = pathlib.Path(selected_file)
        self.tkvars.file_name.set(self.vars.original_path.name)
        self.vars.undo_buffer.clear()
        self.tkvars.buttonstate.apply.set(tkinter.DISABLED)
        self.tkvars.buttonstate.save.set(tkinter.DISABLED)
        self.vars.unapplied_changes = False
        return True

    def show_additional_buttons(self, buttons_area, buttons_grid):
        """Additional buttons for the pixelate_image script"""
        self.widgets.buttons.undo = tkinter.Button(
            buttons_area,
            text="\u238c Undo",
            command=self.revert_last_pixelation,
        )
        self.widgets.buttons.undo.grid(row=0, column=0, **buttons_grid)
        self.widgets.buttons.apply = tkinter.Button(
            buttons_area, text="\u2713 Apply", command=self.apply_pixelation
        )
        self.widgets.buttons.apply.grid(row=0, column=1, **buttons_grid)
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
        self.callbacks.update_buttons()
        return 1


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
        format="%(levelname)-8s\u2551 %(funcName)s → %(message)s",
        level=arguments.loglevel,
    )
    selected_file = arguments.image_file
    if selected_file and not selected_file.is_file():
        selected_file = None
    #
    ImageUI(selected_file, arguments)


if __name__ == "__main__":
    sys.exit(main(__get_arguments()))


# vim: fileencoding=utf-8 ts=4 sts=4 sw=4 autoindent expandtab syntax=python:
