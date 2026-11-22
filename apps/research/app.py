"""app-research: www.iam-624.com/research shows the summary from the site-content ConfigMap."""
import html

from common import Handler, content, page, serve


def article(text):
    title, _, rest = text.strip().partition("\n")
    paragraphs = "".join(f"<p>{html.escape(p.strip())}</p>" for p in rest.split("\n\n") if p.strip())
    return f"<article><h1>{html.escape(title)}</h1>{paragraphs}</article>"


class Research(Handler):
    def route(self, path):
        if path.rstrip("/") == "/research":
            return self.send(200, page("app-research", "Research", article(content()["research.txt"])))
        self.send(404, "not found", "text/plain")


serve(Research)
