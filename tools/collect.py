# -*- coding: utf-8 -*-
"""Collect text evidence into docs/evidence/: kubectl get/describe/logs output and checked HTTP tests.

Needs the 3-node minikube profile exam624 running and the app deployed (deploy.sh / deploy.cmd).
Run from the repository root: python tools/collect.py
Set KUBECTL to a kubectl path if kubectl is not on PATH. Exits with 1 when a test fails.
"""
import datetime
import http.client
import io
import json
import os
import pathlib
import subprocess
import sys
import uuid
from urllib.parse import quote

from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "evidence"
KUBECTL = os.environ.get("KUBECTL", "kubectl")
PROFILE = "exam624"
NS = ["-n", "iam624"]
SEED = (REPO / "content" / "research.txt").read_text(encoding="utf-8")
NAME = (REPO / "content" / "name-th").read_text(encoding="utf-8").strip()
PHOTO = (REPO / "content" / "photo.jpg").read_bytes()
WWW, ALIAS, ADM = "www.iam-624.com", "www.id-624.com", "admin.iam-624.com"


def sh(argv):
    shown = " ".join(["kubectl" if a == KUBECTL else a for a in argv])
    r = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace")
    return f"$ {shown}\n{r.stdout}{r.stderr}".rstrip() + "\n"


def k(*args):
    return [KUBECTL, *args]


def mk(*args):
    return ["minikube", "-p", PROFILE, *args]


def save(name, argvs):
    stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    (OUT / name).write_text(f"# collected {stamp}\n\n" + "\n".join(sh(a) for a in argvs), encoding="utf-8")


def restore_content():
    """Put content/ back into the ConfigMap exactly, the same way deploy.sh first created it."""
    yaml = subprocess.run(k("create", "configmap", "site-content", *NS, "--from-file=content/", "--dry-run=client", "-o", "yaml"),
                          cwd=REPO, capture_output=True, check=True).stdout
    subprocess.run(k("replace", "-f", "-"), input=yaml, capture_output=True, check=True)


IP = subprocess.run(mk("ip"), capture_output=True, text=True, check=True).stdout.strip()


def req(host, method, path, body=None, ctype=None):
    """One request straight to the ingress IP with a Host header; redirects are not followed."""
    c = http.client.HTTPConnection(IP, 80, timeout=15)
    c.request(method, path, body=body, headers={"Host": host, **({"Content-Type": ctype} if ctype else {})})
    r = c.getresponse()
    return r.status, r.getheader("Location", ""), r.getheader("Content-Type", ""), r.read()


def post_form(path, fields, photo=None):
    """multipart/form-data POST to admin.iam-624.com, as the browser form sends it."""
    b = uuid.uuid4().hex
    body = b"".join(f'--{b}\r\nContent-Disposition: form-data; name="{n}"\r\n\r\n'.encode() + v.encode() + b"\r\n"
                    for n, v in fields.items())
    if photo is not None:
        body += (f'--{b}\r\nContent-Disposition: form-data; name="photo"; filename="p.jpg"\r\n'
                 f"Content-Type: image/jpeg\r\n\r\n").encode() + photo + b"\r\n"
    body += f"--{b}--\r\n".encode()
    return req(ADM, "POST", path, body, f"multipart/form-data; boundary={b}")


def footers(host, path, n=30):
    """{(pod, node)} seen in the page footer over n requests."""
    seen = set()
    for _ in range(n):
        tail = req(host, "GET", path)[3].decode("utf-8").rsplit("<footer>", 1)[1]
        seen.add((tail.split("pod ")[1].split(" ")[0], tail.split("node ")[1].split("<")[0].strip()))
    return seen


RESULTS = []


def check(tid, desc, url, expected, got, ok):
    RESULTS.append({"id": tid, "desc": desc, "url": url, "expected": expected, "got": got, "ok": bool(ok)})
    print(("PASS" if ok else "FAIL"), tid, desc, "->", got)


def tests():
    title = SEED.split("\n", 1)[0]
    for tid, host in (("T1", WWW), ("T2", ALIAS)):
        s, _, _, b = req(host, "GET", "/")
        check(tid, f"{host}/ shows photo, name and ID (portal-624)", f"http://{host}/", "200, name, 68130624, <img /photo.jpg>",
              f"{s}, {len(b)}B", s == 200 and NAME.encode() in b and b"68130624" in b and b'src="/photo.jpg"' in b and b"portal-624" in b)
    s, _, t, b = req(WWW, "GET", "/photo.jpg")
    check("T3", "photo is served unchanged from the ConfigMap", f"http://{WWW}/photo.jpg", "200 image/jpeg, same bytes as content/photo.jpg",
          f"{s} {t}, {len(b)}B", s == 200 and t == "image/jpeg" and b == PHOTO)
    for tid, host in (("T4", WWW), ("T5", ALIAS)):
        s, _, _, b = req(host, "GET", "/research")
        check(tid, f"{host}/research shows the summary (app-research)", f"http://{host}/research", "200 and the summary title",
              f"{s}, title {'found' if title.encode() in b else 'missing'}", s == 200 and title.encode() in b and b"app-research" in b)
    got = [req(host, "GET", "/api-624/hello") for host in (WWW, ALIAS)]
    check("T6", "/api-624/<text> shows text big and centred (api-624), on both www names", f"http://{WWW}/api-624/hello, http://{ALIAS}/api-624/hello",
          '200, <main class="big">hello</main> on both', ", ".join(str(g[0]) for g in got),
          all(g[0] == 200 and b'<main class="big">hello</main>' in g[3] and b"api-624" in g[3] for g in got))
    thai = "สวัสดี K8s"
    s, _, _, b = req(WWW, "GET", "/api-624/" + quote(thai))
    check("T7", "/api-624 handles Thai and spaces", f"http://{WWW}/api-624/%E0%B8%AA...%20K8s", "200, Thai text unchanged",
          f"{s}", s == 200 and f'<main class="big">{thai}</main>'.encode() in b)
    s, _, _, b = req(WWW, "GET", "/api-624/" + quote("<b>hi</b>", safe=""))
    check("T8", "/api-624 escapes HTML", f"http://{WWW}/api-624/%3Cb%3Ehi%3C%2Fb%3E", "200, &lt;b&gt;hi&lt;/b&gt;, no raw <b>",
          f"{s}", s == 200 and b"&lt;b&gt;hi&lt;/b&gt;" in b and b"<b>hi</b>" not in b)
    s, _, _, _ = req(WWW, "GET", "/api-624")
    check("T9", "/api-624 without text gives a hint (404)", f"http://{WWW}/api-624", "404", f"{s}", s == 404)
    s, _, _, b = req(ADM, "GET", "/")
    check("T10", "admin menu has the two edit buttons (admin-624)", f"http://{ADM}/", '200, links /portal and /research',
          f"{s}", s == 200 and b'href="/portal"' in b and b'href="/research"' in b and b"admin-624" in b)
    s, _, _, b = req(ADM, "GET", "/portal")
    check("T11", "portal editor shows the current data", f"http://{ADM}/portal", "200, inputs with name and ID, file input",
          f"{s}", s == 200 and NAME.encode() in b and b'type="file"' in b)
    s, _, _, b = req(ADM, "GET", "/research")
    check("T12", "research editor shows the current summary", f"http://{ADM}/research", "200, textarea with the title",
          f"{s}", s == 200 and b"<textarea" in b and title.encode() in b)
    s, _, _, _ = req(WWW, "POST", "/research", b"x", "text/plain")
    check("T13", "the public host cannot save anything", f"POST http://{WWW}/research", "501 (no POST on app-research)", f"{s}", s == 501)

    marker = "[collect-check] "
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (200, 30, 30)).save(buf, "JPEG")
    red = buf.getvalue()
    try:
        s, loc, _, _ = post_form("/research", {"research.txt": marker + SEED})
        seen = {req(WWW, "GET", "/research")[3].decode().count(marker) for _ in range(15)}
        check("T14", "research edit is shown at once by every replica", f"POST http://{ADM}/research", "303, then 15 reads all show it",
              f"{s} -> {loc}, reads {sorted(seen)}", s == 303 and loc.endswith("/research?saved=1") and seen == {1})
        s, loc, _, _ = post_form("/portal", {"name-th": marker + NAME, "name-en": "Pathomtad Phoovanakulchai", "student-id": "68130624"}, red)
        seen = {marker.encode() in req(WWW, "GET", "/")[3] for _ in range(15)}
        got_photo = req(WWW, "GET", "/photo.jpg")[3]
        check("T15", "portal edit (name and photo) is shown at once", f"POST http://{ADM}/portal", "303, 15 reads show the name, new photo",
              f"{s} -> {loc}, reads {sorted(seen)}, photo {'new' if got_photo == red else 'old'}",
              s == 303 and seen == {True} and got_photo == red)
        s1, _, _, _ = post_form("/portal", {"name-th": "x", "name-en": "x", "student-id": "x"}, b"GIF89a not a jpeg")
        s2, _, _, _ = post_form("/research", {"research.txt": "   "})
        s3, _, _, _ = post_form("/portal", {"name-th": "", "name-en": "x", "student-id": "x"})
        unchanged = marker.encode() in req(WWW, "GET", "/")[3]
        check("T16", "invalid input is refused and nothing is saved", f"POST http://{ADM}/portal and /research",
              "400 for non-JPEG photo, empty summary, empty name", f"{s1}, {s2}, {s3}, data {'unchanged' if unchanged else 'CHANGED'}",
              (s1, s2, s3) == (400, 400, 400) and unchanged)
    finally:
        restore_content()
    s, _, _, b = req(WWW, "GET", "/")
    b2 = req(WWW, "GET", "/research")[3]
    check("T17", "original content restored after the tests", f"http://{WWW}/ and /research", "no marker, original photo",
          f"{s}", marker.encode() not in b + b2 and req(WWW, "GET", "/photo.jpg")[3] == PHOTO)
    s, _, _, _ = req(WWW, "HEAD", "/")
    check("T18", "HEAD works", f"HEAD http://{WWW}/", "200", f"{s}", s == 200)
    nodes = subprocess.run(k("get", "nodes", "-o", "jsonpath={range .items[*]}{.metadata.name} {end}"), capture_output=True, text=True).stdout.split()
    for sub, app, host, path in [("a", "portal-624", WWW, "/"), ("b", "app-research", WWW, "/research"),
                                 ("c", "api-624", WWW, "/api-624/x"), ("d", "admin-624", ADM, "/")]:
        seen = footers(host, path)
        check("T19" + sub, f"{app}: 3 Pods on 3 different nodes answer", f"http://{host}{path} x30", "3 Pods, 3 nodes",
              "; ".join(f"{p} @ {n}" for p, n in sorted(seen)), len({p for p, _ in seen}) == 3 and {n for _, n in seen} == set(nodes))
    ready = subprocess.run(k("get", "deploy", *NS, "-o", "jsonpath={range .items[*]}{.metadata.name}={.status.availableReplicas}/{.spec.replicas} {end}"),
                           capture_output=True, text=True).stdout.strip()
    check("T20", "3 nodes Ready, all 4 Deployments 3/3", "kubectl get nodes; kubectl get deploy -n iam624", "3 nodes, 3/3 each",
          f"nodes: {' '.join(nodes)}; {ready}", len(nodes) == 3 and ready.count("=3/3") == 4)
    can = lambda verb, sa, res="configmap/site-content": subprocess.run(
        k("auth", "can-i", verb, res, *NS, f"--as=system:serviceaccount:iam624:{sa}"), capture_output=True, text=True).stdout.strip()
    got = {"reader get": can("get", "content-reader"), "reader patch": can("patch", "content-reader"),
           "editor patch": can("patch", "content-editor"), "editor patch other cm": can("patch", "content-editor", "configmap/portal-code"),
           "default get": can("get", "default")}
    check("T21", "RBAC: only admin-624's ServiceAccount may change site-content", "kubectl auth can-i ... --as=<ServiceAccount>",
          "reader get yes, reader patch no, editor patch yes, editor other no, default no", ", ".join(f"{k_} {v}" for k_, v in got.items()),
          list(got.values()) == ["yes", "no", "yes", "no", "no"])


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    save("01-cluster.txt", [["minikube", "version"], mk("status"), mk("ip"), k("version"), k("get", "nodes", "-o", "wide"),
                            k("get", "ingressclass"), k("get", "pods,svc", "-n", "ingress-nginx", "-o", "wide")])
    save("02-get.txt", [k("get", "deploy,rs,svc,ingress", *NS, "-o", "wide"), k("get", "pods", *NS, "-o", "wide", "--sort-by=.spec.nodeName"),
                        k("get", "configmap,serviceaccount,role,rolebinding", *NS), k("get", "endpointslices", *NS)])
    save("03-describe-ingress.txt", [k("describe", "ingress", *NS)])
    save("04-describe-workload.txt", [k("describe", "svc", *NS), k("describe", "deploy", "admin-624", *NS),
                                      k("describe", "configmap", "site-content", *NS)])
    ssh = lambda node, c: mk("ssh", "-n", node, "--", c)
    save("06-linux-hosts.txt", [ssh("exam624-m02", f"grep -q iam-624 /etc/hosts || echo '{IP}  {WWW}  {ADM}  {ALIAS}' | sudo tee -a /etc/hosts"),
                                ssh("exam624-m02", "cat /etc/hosts"),
                                ssh("exam624-m02", "curl -s http://www.iam-624.com/ | grep -o 'pod portal-624[^<]*'"),
                                ssh("exam624-m02", "curl -s http://www.id-624.com/research | grep -o 'pod app-research[^<]*'"),
                                ssh("exam624-m02", "curl -s http://admin.iam-624.com/ | grep -o 'pod admin-624[^<]*'")])
    save("07-rbac.txt", [k("describe", "role,rolebinding", *NS)] + [
        k("auth", "can-i", v, "configmap/site-content", *NS, f"--as=system:serviceaccount:iam624:{sa}")
        for v, sa in [("get", "content-reader"), ("patch", "content-reader"), ("patch", "content-editor"), ("delete", "content-editor")]])
    tests()
    save("05-logs.txt", [k("logs", f"deploy/{d}", *NS, "--tail=5") for d in ("portal-624", "app-research", "api-624", "admin-624")])
    (OUT / "results.json").write_text(json.dumps(
        {"time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ip": IP, "results": RESULTS}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    bad = [r["id"] for r in RESULTS if not r["ok"]]
    print("FAILED:", bad if bad else "none")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
