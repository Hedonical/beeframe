import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


class NoCacheHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


parser = argparse.ArgumentParser()
parser.add_argument("directory", nargs="?", default="build-site")
parser.add_argument("--port", type=int, default=8008)
args = parser.parse_args()

handler = partial(NoCacheHandler, directory=args.directory)
server = ThreadingHTTPServer(("localhost", args.port), handler)
print(f"Serving {args.directory} at http://localhost:{args.port}")
server.serve_forever()
