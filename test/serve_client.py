#!/usr/bin/env python3
"""
Simple HTTP server to serve test/client.html on the local network.

- binds to 0.0.0.0 so other devices on the same LAN can access it
- serves files from the `test/` directory (script's directory)
- requests to `/` return `client.html`

Usage:
    python serve_client.py --port 8000
Then open http://<server-ip>:8000/ on your phone or other LAN device.
"""
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from functools import partial
from pathlib import Path
import argparse
import socket
import sys


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # doesn't actually connect; used to determine the default outbound IP
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        try:
            s.close()
        except Exception:
            pass


def make_handler(directory):
    class ClientHandler(SimpleHTTPRequestHandler):
        # serve client.html for root
        def do_GET(self):
            if self.path in ('', '/'):
                self.path = '/client.html'
            return super().do_GET()

    return partial(ClientHandler, directory=directory)


def main():
    p = argparse.ArgumentParser(description='Serve test/client.html on LAN')
    p.add_argument('--port', '-p', type=int, default=8000, help='Port to listen on')
    args = p.parse_args()

    directory = str(Path(__file__).resolve().parent)
    handler = make_handler(directory)

    server_address = ('0.0.0.0', args.port)
    httpd = ThreadingHTTPServer(server_address, handler)

    lan_ip = get_lan_ip()
    print('Serving directory:', directory)
    print(f' - Local:  http://0.0.0.0:{args.port}/')
    print(f' - LAN:    http://{lan_ip}:{args.port}/  (use this on other devices)')
    print('Press Ctrl-C to stop')

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\nStopping server...')
        httpd.server_close()


if __name__ == '__main__':
    main()
