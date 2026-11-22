"""Shared by all four services: page template, security headers, HTTP server, and the site-content ConfigMap.

The editable data (name, student ID, photo, research summary) lives in the ConfigMap `site-content`.
Pods read and write it through the Kubernetes API with their ServiceAccount token, so every Pod on every
node sees an edit at once. A mounted ConfigMap volume would lag by up to a minute.
"""
import base64
import html
import json
import os
import signal
import socket
import ssl
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

POD = os.environ.get("HOSTNAME", socket.gethostname())
NODE = os.environ.get("NODE_NAME", "?")
SA = "/var/run/secrets/kubernetes.io/serviceaccount"
STYLE = """
:root{color-scheme:light dark}
body{margin:0;padding-bottom:3rem;font-family:system-ui,"Leelawadee UI","Noto Sans Thai",Tahoma,sans-serif;line-height:1.7}
main,article{max-width:46rem;margin:0 auto;padding:2rem 1.25rem}
footer{position:fixed;left:0;right:0;bottom:0;padding:.5rem;text-align:center;font-size:.75rem;opacity:.75;background:Canvas}
input,textarea{width:100%;box-sizing:border-box;padding:.5rem;font:inherit}
button,.btn{display:inline-block;padding:.6rem 1.6rem;font:inherit;border-radius:8px;border:1px solid #2b6cb0;
  background:#2b6cb0;color:#fff;text-decoration:none;cursor:pointer}
"""


def page(app, title, body, css=""):
    return (f'<!doctype html><html lang="th"><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{html.escape(title)}</title><style>{STYLE}{css}</style>{body}"
            f"<footer>ปฐมทัศน์ ภูวนกุลชัย 68130624 · {app} · pod {POD} · node {NODE}</footer></html>")


def _api(method="GET", body=None):
    ns = open(f"{SA}/namespace").read()
    req = urllib.request.Request(
        f"https://kubernetes.default.svc/api/v1/namespaces/{ns}/configmaps/site-content", method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"Authorization": "Bearer " + open(f"{SA}/token").read(),  # re-read: the kubelet rotates it
                 "Content-Type": "application/merge-patch+json"})
    ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")
    with urllib.request.urlopen(req, context=ctx, timeout=5) as r:
        return json.load(r)


def content():
    """Text keys as str, plus 'photo.jpg' as bytes."""
    cm = _api()
    data = {k: v.strip() for k, v in cm.get("data", {}).items()}
    data["photo.jpg"] = base64.b64decode(cm.get("binaryData", {}).get("photo.jpg", ""))
    return data


def save_content(text=None, photo=None):
    """Merge-patch: only the given keys change."""
    _api("PATCH", {"data": text or {}, "binaryData": {"photo.jpg": base64.b64encode(photo).decode()} if photo else {}})


class Handler(BaseHTTPRequestHandler):
    """Subclasses define route(path); POST is optional."""

    def send(self, status, body, ctype="text/html; charset=utf-8", headers=()):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; form-action 'self'")
        for key, value in headers:
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def redirect(self, to, status=302):
        self.send(status, "", headers=[("Location", to)])

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            return self.send(200, "ok", "text/plain")
        try:
            self.route(path)
        except OSError as e:  # API server or ConfigMap not reachable: say so instead of dropping the connection
            self.log_error("content: %r", e)
            self.send(503, "site-content not available, try again", "text/plain; charset=utf-8")

    do_HEAD = do_GET


def serve(handler):
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # Pod deletion: exit 0, not "Error" (killed by signal)
    ThreadingHTTPServer(("", 8080), handler).serve_forever()
