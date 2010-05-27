from distutils.core import setup, Extension
module1 = Extension('xinputextdev',
        include_dirs = [
            '/usr/include/pygtk-2.0',
            '/usr/include/glib-2.0',
            '/usr/include/cairo',
            '/usr/include/pango-1.0',
            '/usr/lib/glib-2.0/include',
            '/usr/lib/gtk-2.0/include',
            '/usr/include/gtk-2.0',
            '/usr/include/glib-2.0',
            '/usr/include/atk-1.0'
            ],

        libraries=[
            #'gtk',
            #'gdk',
            #'pygtk',
            'gtk-x11-2.0',
            'X11',
            'Xi', 'Xtst'],
        sources = ['xinputextdev.c'])

setup (name = 'PackageName',
        version = '1.0',
        description = 'Interaction with Xinput extension device',
        ext_modules = [module1])
