# File manager integration

The **autoselect.py** script can be integrated with some file managers
to call the pixelation scripts using one or two clicks in the
context menu after selecting a file.

## Nautilus (GNOME)

Install Nautilus script integration:

```
autoselect.py --install-nautilus-script
```

This will install **autoselect.py** as a Nautilus script
(located in the "Scripts" submenu ot the context menu.

If you provide a name after `--install-nautilus-script`, the script will be
installed with that name, otherwise as `Pixelate`.

## Thunar (XFCE)

Add the command `autoselect.py %f`
(with its full path as printed by `readlink -f`)
to Thunar using a custom action as documented in
<https://docs.xfce.org/xfce/thunar/custom-actions>.

Select "Image files" and "Video files" on the "Appearance Conditions" tab.

## Windows Explorer

Create a new `.cmd` file containing the following:

```
start pythonw \path\to\autoselect.py %1
```

(replace `\path\to` with the actual path of **autoselect.py**)
and put a link to that file into the `%APPDATA%\Microsoft\Windows\SendTo` directory.

Having done that, every time you right-click a file in Windows Explorer,
the link created in the previous step will appear
in the **Send to** submenu of the context menu.
