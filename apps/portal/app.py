"""portal-624: www.iam-624.com/ shows the photo and the name from the site-content ConfigMap."""
import html

from common import Handler, content, page, serve

CSS = "nav{display:flex;gap:.75rem;justify-content:center;flex-wrap:wrap;margin-top:1.5rem}"


class Portal(Handler):
    def route(self, path):
        if path == "/":
            c = content()
            name = html.escape(c.get("name-th", ""))
            body = f"""<main style="text-align:center">
<img src="/photo.jpg" alt="{name}" style="width:min(240px,70vw);border-radius:16px">
<h1 style="margin-bottom:0">{name}</h1>
<p style="margin-top:0">{html.escape(c.get("name-en", ""))}</p>
<p style="font-size:1.5rem;font-weight:700">{html.escape(c.get("student-id", ""))}</p>
<nav><a class="btn" href="/research">สรุปงานวิจัย</a><a class="btn" href="/api-624/สวัสดี K8s">ตัวอย่าง api-624</a></nav>
</main>"""
            return self.send(200, page("portal-624", "Portal 624", body, CSS))
        if path == "/photo.jpg":
            return self.send(200, content()["photo.jpg"], "image/jpeg")
        self.send(404, "not found", "text/plain")


serve(Portal)
