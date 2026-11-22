"""api-624: www.iam-624.com/api-624/<text> shows <text> big, in the middle of the screen."""
import html
from urllib.parse import unquote

from common import Handler, page, serve

PREFIX = "/api-624/"
CSS = ("main.big{min-height:100vh;display:grid;place-items:center;box-sizing:border-box;max-width:none;"
       "font-size:clamp(2.5rem,12vw,9rem);font-weight:700;line-height:1.2;text-align:center;overflow-wrap:anywhere}")


class Api(Handler):
    def route(self, path):
        if path.startswith(PREFIX) and len(path) > len(PREFIX):
            text = unquote(path[len(PREFIX):])  # browsers send UTF-8 percent-encoding
            return self.send(200, page("api-624", text[:80], f'<main class="big">{html.escape(text)}</main>', CSS))
        self.send(404, "use /api-624/<text>", "text/plain")


serve(Api)
