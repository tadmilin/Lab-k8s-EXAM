"""admin-624: admin.iam-624.com shows two buttons, one to edit the portal data and one to edit the research summary.

Saving patches the site-content ConfigMap, so www.iam-624.com changes at once on every Pod.
"""
import html
from email.parser import BytesParser
from email.policy import HTTP

from common import Handler, content, page, save_content, serve

MAX_BODY = 1_000_000          # bytes for the whole form
MAX_PHOTO = 600_000           # base64 grows it to ~800 KB; a ConfigMap holds at most 1 MiB
FIELDS = {"name-th": "ชื่อ (ภาษาไทย)", "name-en": "ชื่อ (ภาษาอังกฤษ)", "student-id": "รหัสนักศึกษา"}
CSS = ("label{display:block;margin:.4rem 0}input{padding:.35rem .5rem}main{padding-top:1rem}nav{display:flex;gap:1rem;justify-content:center;flex-wrap:wrap;margin:2rem 0}"
       "nav .btn{font-size:1.25rem;padding:1.2rem 2rem;min-width:14rem}")
BACK = '<p><a href="/">« กลับเมนู</a> · <a href="http://www.iam-624.com/">เปิด www.iam-624.com</a></p>'
SAVED = '<p style="color:green"><b>บันทึกแล้ว</b> หน้าเว็บ www.iam-624.com เปลี่ยนแล้ว</p>'


def menu():
    return page("admin-624", "Admin iam-624", f"""<main style="text-align:center"><h1>ผู้ดูแลระบบ iam-624</h1>
<p>เลือกข้อมูลที่ต้องการแก้ไข</p>
<nav><a class="btn" href="/portal">แก้ไขข้อมูล Portal</a><a class="btn" href="/research">แก้ไขสรุปงานวิจัย</a></nav>
<p><a href="http://www.iam-624.com/">เปิด www.iam-624.com</a></p></main>""", CSS)


def portal_form(saved, error=""):
    c = content()
    inputs = "".join(f'<label>{label}<input name="{key}" value="{html.escape(c.get(key, ""))}" required maxlength="120"></label>'
                     for key, label in FIELDS.items())
    return page("admin-624", "แก้ไขข้อมูล Portal", f"""<main><h1>แก้ไขข้อมูล Portal</h1>{SAVED if saved else ""}{error}
<form method="post" action="/portal" enctype="multipart/form-data">{inputs}
<div style="display:flex;gap:1rem;align-items:center"><img src="/photo.jpg" alt="รูปปัจจุบัน" style="width:110px;border-radius:8px">
<label style="flex:1">เปลี่ยนรูป (JPEG ไม่เกิน 600 KB, เว้นว่างไว้ถ้าไม่เปลี่ยน)<input type="file" name="photo" accept="image/jpeg"></label></div>
<p><button>บันทึก</button></p></form>{BACK}</main>""", CSS)


def research_form(saved, error=""):
    return page("admin-624", "แก้ไขสรุปงานวิจัย", f"""<main><h1>แก้ไขสรุปงานวิจัย</h1>{SAVED if saved else ""}{error}
<form method="post" action="/research" enctype="multipart/form-data">
<p style="margin:.25rem 0">บรรทัดแรกคือหัวข้อ เว้นบรรทัดว่างหนึ่งบรรทัดเพื่อขึ้นย่อหน้าใหม่</p>
<textarea name="research.txt" rows="11" required>{html.escape(content()["research.txt"])}</textarea>
<p><button>บันทึก</button></p></form>{BACK}</main>""", CSS)


def bad(msg):
    return f'<p style="color:#b00020"><b>ไม่ได้บันทึก:</b> {html.escape(msg)}</p>'


class Admin(Handler):
    def route(self, path):
        saved = "saved=1" in self.path
        if path == "/":
            return self.send(200, menu())
        if path == "/portal":
            return self.send(200, portal_form(saved))
        if path == "/research":
            return self.send(200, research_form(saved))
        if path == "/photo.jpg":
            return self.send(200, content()["photo.jpg"], "image/jpeg")
        self.send(404, "not found", "text/plain")

    def form(self):
        """multipart/form-data fields as {name: bytes}; empty when the body is not multipart."""
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        msg = BytesParser(policy=HTTP).parsebytes(
            b"Content-Type: " + (self.headers.get("Content-Type") or "").encode() + b"\r\n\r\n" + raw)
        if not msg.is_multipart():
            return {}
        return {p.get_param("name", header="content-disposition"): p.get_payload(decode=True) or b""
                for p in msg.iter_parts()}

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        if path not in ("/portal", "/research"):
            return self.send(404, "not found", "text/plain")
        if int(self.headers.get("Content-Length") or 0) > MAX_BODY:
            return self.send(413, "too large", "text/plain")
        try:
            f = self.form()
            if path == "/research":
                text = f.get("research.txt", b"").decode("utf-8").replace("\r\n", "\n").strip()
                if not text:
                    return self.send(400, research_form(False, bad("ข้อความว่าง")))
                save_content({"research.txt": text + "\n"})
            else:
                text = {k: f.get(k, b"").decode("utf-8").strip() for k in FIELDS}
                photo = f.get("photo", b"")
                if not all(text.values()) or max(map(len, text.values())) > 120:
                    return self.send(400, portal_form(False, bad("ต้องกรอกทุกช่อง และไม่เกิน 120 ตัวอักษร")))
                if photo and (len(photo) > MAX_PHOTO or not photo.startswith(b"\xff\xd8\xff")):
                    return self.send(400, portal_form(False, bad("รูปต้องเป็น JPEG ขนาดไม่เกิน 600 KB")))
                save_content(text, photo)
        except UnicodeDecodeError:
            return self.send(400, "form must be UTF-8", "text/plain")
        except OSError as e:
            self.log_error("save: %r", e)
            return self.send(503, "could not save site-content, try again", "text/plain; charset=utf-8")
        self.redirect(path + "?saved=1", 303)


serve(Admin)
