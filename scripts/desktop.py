"""Stable localhost origin; user data is stored in browser IndexedDB, outside code."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from functools import partial
import webbrowser


def main():
    root = Path(__file__).resolve().parents[1] / 'dist'
    if not (root / 'index.html').exists():
        raise SystemExit('먼저 npm install 후 npm run build를 실행하세요.')
    server = ThreadingHTTPServer(('127.0.0.1', 8765), partial(SimpleHTTPRequestHandler, directory=str(root)))
    print('Worship Guide: http://localhost:8765 · 종료하려면 Ctrl+C')
    webbrowser.open('http://localhost:8765')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
