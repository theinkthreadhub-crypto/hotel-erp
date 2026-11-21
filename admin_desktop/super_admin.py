"""HoReCa One Super Admin for Windows: the vendor's control panel (create hotels, licences, Login Cards, backups,
tickets) in its own desktop window. It opens the live Super Admin page on hotel.setupro.in, so it is always the
same version as the Android app and the website; nothing about hotels is stored on this PC except the window's own
sign-in (the Admin Key is kept only if "Remember" is ticked, in this user's WebView2 profile).

Built by .github/workflows/build-super-admin-exe.yml (PyInstaller + Inno Setup).
"""
import os
import sys
import webbrowser

URL = 'https://hotel.setupro.in/admin'
APP_VERSION = 'dev'          # stamped by the build


def data_dir():
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    d = os.path.join(base, 'HoReCaOneSuperAdmin')
    os.makedirs(d, exist_ok=True)
    return d


def resource(name):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, name)
    return p if os.path.exists(p) else None


def main():
    try:
        import webview
    except Exception:
        webbrowser.open(URL)                      # no window toolkit: the browser shows the same page
        return
    try:
        webview.settings['ALLOW_DOWNLOADS'] = True             # backups, CSV, Login Card files
        webview.settings['OPEN_EXTERNAL_LINKS_IN_BROWSER'] = True   # WhatsApp share, help links
    except Exception:
        pass
    webview.create_window(title=f'HoReCa One Super Admin {APP_VERSION}', url=URL, width=1280, height=860,
                          min_size=(900, 640), resizable=True, text_select=True, zoomable=True)
    try:
        # Edge WebView2 by name: without it the page would load in old IE; failing here opens the browser instead
        webview.start(gui='edgechromium' if os.name == 'nt' else None, private_mode=False,
                      storage_path=data_dir(), icon=resource('favicon.ico'))
    except Exception:
        webbrowser.open(URL)


if __name__ == '__main__':
    main()
