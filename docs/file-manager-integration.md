# File manager integration

The **pixelate.py** script can be integrated with some file managers
to call the pixelation scripts using one or two clicks in the
context menu after selecting a file.

## Nautilus / Nemo (GNOME) script

Install Nautilus script:

```
pixelate.py --install-nautilus-script [ Name ]
```

Install Nemo script:

```
pixelate.py --install-nemo-script [ Name ]
```

This will install **pixelate.py** as a script for the selected file manager
(located in the "Scripts" submenu ot the context menu.

`Name` defaults to `Pyxelate`.

## Nemo (GNOME) action

Install Nautilus action:

```
pixelate.py --install-nemo-action [ Name [ Comment ] ]
```

This will install **pixelate.py** as a Nemo action.

`Name` defaults to `Pyxelate`,
`Comment` to `"pixelate images or video sequences"`.

## Thunar (XFCE) custom action

Add the command `pixelate.py %f`
(with its full path as printed by `readlink -f`)
to Thunar using a custom action as documented in
<https://docs.xfce.org/xfce/thunar/custom-actions>.

Select "Image files" and "Video files" on the "Appearance Conditions" tab.

## Windows Explorer (send to …)

Create a new `.cmd` file containing the following:

```
start pythonw \path\to\pixelate.py %1
```

(replace `\path\to` with the actual path of **pixelate.py**)
and put a link to that file into the `%APPDATA%\Microsoft\Windows\SendTo` directory.

Having done that, every time you right-click a file in Windows Explorer,
the link created in the previous step will appear
in the **Send to** submenu of the context menu.
