# -*- coding: utf-8 -*-
"""
Setu - Restaurant & Hotel POS - Standalone Desktop Launcher
Powered by Aghanya Devanya Enterprises
"""
import os
import sys
import socket
import threading
import http.server
import socketserver
import webview

def get_base_dir():
    # If running as PyInstaller bundled executable
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # If user has hotel_erp.html placed right next to .exe, prioritize it
        if os.path.exists(os.path.join(exe_dir, 'hotel_erp.html')):
            return exe_dir
        if hasattr(sys, '_MEIPASS'):
            return sys._MEIPASS
        return exe_dir
    return os.path.dirname(os.path.abspath(__file__))

def find_free_port(preferred=8000):
    # Try preferred port first
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', preferred)) != 0:
            return preferred
    # Otherwise find any free available ephemeral port
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]

def run_server(base_dir, port):
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=base_dir, **kwargs)
        def log_message(self, format, *args):
            pass  # suppress log output

    try:
        with socketserver.TCPServer(('127.0.0.1', port), QuietHandler) as httpd:
            httpd.serve_forever()
    except Exception as e:
        print(f"Server error on port {port}: {e}")

def main():
    base_dir = get_base_dir()
    port = find_free_port(8000)

    # Start embedded HTTP server in background thread
    server_thread = threading.Thread(target=run_server, args=(base_dir, port), daemon=True)
    server_thread.start()

    # User data directory on Windows (%LOCALAPPDATA%\AghanyaDevanyaERP\Data)
    local_app_data = os.environ.get('LOCALAPPDATA', os.path.expanduser('~'))
    storage_dir = os.path.join(local_app_data, 'AghanyaDevanyaERP', 'Data')
    os.makedirs(storage_dir, exist_ok=True)

    icon_path = os.path.join(base_dir, 'favicon.ico')
    if not os.path.exists(icon_path):
        icon_path = None

    url = f"http://127.0.0.1:{port}/hotel_erp.html"

    # Create native desktop window
    window = webview.create_window(
        title='Setu - Restaurant & Hotel POS',
        url=url,
        width=1340,
        height=860,
        min_size=(1020, 680),
        resizable=True,
        text_select=True,
        zoomable=True
    )

    webview.start(
        private_mode=False,
        storage_path=storage_dir,
        icon=icon_path
    )

if __name__ == '__main__':
    main()
