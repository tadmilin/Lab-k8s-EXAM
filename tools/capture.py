# -*- coding: utf-8 -*-
"""Capture evidence screenshots of real windows (Chrome and PowerShell consoles), never the whole screen.

Chrome is driven over the DevTools protocol (typing, clicking, choosing a file). Each step is grabbed with
PrintWindow, so the address bar with www.iam-624.com / admin.iam-624.com is visible. Chrome maps the names to
the minikube IP with a flag, so the Windows hosts file stays untouched.

Needs: Windows, Chrome, minikube profile exam624 running with the app deployed, `pip install pillow websocket-client`.
Run from the repository root:  python tools/capture.py
Set KUBECTL to a kubectl.exe path if kubectl is not on PATH. Output: docs/screenshots/*.png + shots.json.
"""
import ctypes
import ctypes.wintypes as W
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request
from urllib.parse import quote

import websocket
from PIL import Image

REPO = pathlib.Path(__file__).resolve().parent.parent
OUT = REPO / "docs" / "screenshots"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
KUBECTL = os.environ.get("KUBECTL", "kubectl")
MARK = "[admin-edit-8421] "  # typed in front of the name and the research title through the admin page
PROFILE = "exam624"
HOSTS = ("www.iam-624.com", "admin.iam-624.com", "www.id-624.com")
COLS, LINES = 150, 60

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
dwmapi = ctypes.WinDLL("dwmapi")
user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))  # per-monitor v2: real pixel sizes
for fn, res, args in [
    (user32.GetWindowDC, ctypes.c_void_p, [W.HWND]),
    (user32.ReleaseDC, ctypes.c_int, [W.HWND, ctypes.c_void_p]),
    (user32.PrintWindow, W.BOOL, [W.HWND, ctypes.c_void_p, W.UINT]),
    (gdi32.CreateCompatibleDC, ctypes.c_void_p, [ctypes.c_void_p]),
    (gdi32.CreateCompatibleBitmap, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]),
    (gdi32.SelectObject, ctypes.c_void_p, [ctypes.c_void_p, ctypes.c_void_p]),
    (gdi32.GetDIBits, ctypes.c_int, [ctypes.c_void_p, ctypes.c_void_p, W.UINT, W.UINT, ctypes.c_void_p,
                                     ctypes.c_void_p, W.UINT]),
    (gdi32.DeleteObject, W.BOOL, [ctypes.c_void_p]),
    (gdi32.DeleteDC, W.BOOL, [ctypes.c_void_p]),
]:
    fn.restype, fn.argtypes = res, args


class BIH(ctypes.Structure):
    _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                ("biClrImportant", W.DWORD)]


def grab(hwnd):
    """PrintWindow(PW_RENDERFULLCONTENT) of one window, cropped to its visible frame."""
    r, f = W.RECT(), W.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(f), ctypes.sizeof(f))  # DWMWA_EXTENDED_FRAME_BOUNDS
    w, h = r.right - r.left, r.bottom - r.top
    hdc = user32.GetWindowDC(hwnd)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, h)
    old = gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)
    gdi32.SelectObject(mdc, old)
    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(hwnd, hdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    return img.crop((f.left - r.left, f.top - r.top, f.right - r.left, f.bottom - r.top))


def windows(match):
    found = []
    proto = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) and match(hwnd):
            found.append(hwnd)
        return True
    user32.EnumWindows(proto(cb), 0)
    return found


def title_of(hwnd):
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


def pid_of(hwnd):
    owner = W.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
    return owner.value


def kill_tree(pid):
    subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)


def trim_bottom(img, top=60, margin=14, scrollbar=40):
    """Drop the empty console rows below the last line of output."""
    body = img.crop((0, top, img.width - scrollbar, img.height)).convert("L").point(lambda v: 255 if v > 70 else 0)
    box = body.getbbox()
    return img if not box else img.crop((0, 0, img.width, min(img.height, top + box[3] + margin)))


PS_HEAD = """$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PATH += ';C:\\Program Files (x86)\\VMware\\VMware Workstation'
{alias}
Set-Location '{here}'
$Host.UI.RawUI.WindowTitle = '{title} | ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
mode con cols={cols} lines={lines}
Clear-Host
function Show([string]$c) {{
  Write-Host ('PS ' + $PWD.Path + '> ') -NoNewline
  Write-Host $c -ForegroundColor Yellow
}}
Write-Host ('# ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' | {label}') -ForegroundColor Cyan
"""


def terminal(name, label, cmds):
    """Run commands in a new console window (conhost + PowerShell) and capture that window only."""
    title = f"evidence-{name}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp = pathlib.Path(tmp)
        marker = tmp / "done"
        alias = f"Set-Alias kubectl '{KUBECTL}'" if KUBECTL != "kubectl" else ""
        body = PS_HEAD.format(alias=alias, here=REPO, title=title, cols=COLS, lines=LINES, label=label)
        # script scope, so variables such as $ip survive between commands
        body += "".join(f"Show @'\n{c}\n'@\nInvoke-Expression @'\n{c}\n'@ | Out-Host\n" for c in cmds)
        body += f"Set-Content -LiteralPath '{marker}' done\n"
        script = tmp / f"{name}.ps1"
        script.write_text(body, encoding="utf-8-sig")
        started = datetime.datetime.now()
        p = subprocess.Popen(["conhost.exe", "powershell.exe", "-NoProfile", "-NoExit", "-ExecutionPolicy",
                              "Bypass", "-File", str(script)], creationflags=subprocess.CREATE_NEW_CONSOLE)
        try:
            deadline = time.time() + 240
            while not marker.exists() and time.time() < deadline:
                time.sleep(0.5)
            time.sleep(1.5)  # let the final prompt render
            found = windows(lambda h: title_of(h).startswith(title + " | "))
            if not found:
                raise RuntimeError(f"window {title} not found")
            img = trim_bottom(grab(found[0]))
        finally:
            kill_tree(p.pid)
    img.save(OUT / f"{name}.png")
    print(f"{name}.png {img.size}")
    return {"file": f"{name}.png", "kind": "terminal", "label": label, "cmds": cmds,
            "time": started.strftime("%Y-%m-%d %H:%M:%S")}


class Chrome:
    """One real Chrome window with its own profile, driven by DevTools, captured by PrintWindow."""

    def __init__(self, ip, port=9333, extra=()):
        rules = ", ".join(f"MAP {h} {ip}" for h in HOSTS)
        self.prof = tempfile.mkdtemp()
        # show full URLs: by default Chrome hides "www." and "http://" in the address bar
        (pathlib.Path(self.prof) / "Default").mkdir()
        (pathlib.Path(self.prof) / "Default" / "Preferences").write_text('{"omnibox":{"prevent_url_elisions":true}}')
        self.proc = subprocess.Popen([
            CHROME, *extra, f"--user-data-dir={self.prof}", f"--remote-debugging-port={port}",
            # --test-type hides the "unsupported command-line flag" bar that --host-resolver-rules would show
            f"--host-resolver-rules={rules}", "--test-type", "--no-first-run", "--no-default-browser-check", "--disable-sync",
            "--disable-gpu", "--disable-gpu-compositing",
            # keep painting when another window covers Chrome; stop Chrome 154+ from upgrading our http:// URLs to
            # https:// (the ingress has no certificate, so the upgrade ends in ERR_BLOCKED_BY_CLIENT)
            "--disable-features=CalculateNativeWinOcclusion,HttpsUpgrades,HttpsFirstBalancedMode,"
            "HttpsFirstBalancedModeAutoEnable,HttpsFirstModeV2ForTypicallySecureUsers,HttpsFirstModeV2ForEngagedSites,"
            "HttpsFirstModeForEngagedSites,HttpsFirstModeIncognito,HttpsFirstModeWithEngagementHeuristic",
            "--disable-backgrounding-occluded-windows",
            "--window-position=40,40", "--window-size=1280,820", "--new-window", "about:blank"])
        for _ in range(60):
            try:
                targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=2))
                page = next(t for t in targets if t["type"] == "page")
                break
            except Exception:
                time.sleep(0.5)
        else:
            raise RuntimeError("chrome DevTools did not start")
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0

    def cmd(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr):
        return self.cmd("Runtime.evaluate", expression=expr, returnByValue=True)["result"].get("value")

    def wait_loaded(self, contains):
        time.sleep(0.5)
        for _ in range(60):
            if self.js("document.readyState") == "complete" and contains in self.js("location.href") and not self.js("window.__old"):
                return
            time.sleep(0.5)
        raise RuntimeError(f"page did not load: {contains}")

    def choose_file(self, selector, path):
        root = self.cmd("DOM.getDocument")["root"]["nodeId"]
        node = self.cmd("DOM.querySelector", nodeId=root, selector=selector)["nodeId"]
        self.cmd("DOM.setFileInputFiles", files=[str(path)], nodeId=node)

    def go(self, url, contains=None):
        self.js("window.__old = 1")  # gone once the new page loads, so wait_loaded cannot match the previous page
        self.cmd("Page.navigate", url=url)
        self.wait_loaded(contains or url.split("//", 1)[1])
        self.unselect()

    def unselect(self):
        for kind in ("mousePressed", "mouseReleased"):  # click the page margin so the address bar is not left selected
            self.cmd("Input.dispatchMouseEvent", type=kind, x=4, y=400, button="left", clickCount=1)

    def shot(self, name, label, url_note="", settle=1.0):
        time.sleep(settle)
        def area(h):
            r = W.RECT()
            user32.GetWindowRect(h, ctypes.byref(r))
            return (r.right - r.left) * (r.bottom - r.top)
        # the process also owns small helper windows; the browser window is the biggest one
        hwnd = max(windows(lambda h: pid_of(h) == self.proc.pid), key=area)
        for _ in range(20):
            img = grab(hwnd)
            lo, hi = img.crop((0, 160, img.width, img.height)).convert("L").getextrema()
            if hi - lo > 40:  # first frames can be blank under PrintWindow
                break
            time.sleep(1)
        else:
            raise RuntimeError("chrome page stayed blank")
        img.save(OUT / f"{name}.png")
        print(f"{name}.png {img.size}")
        return {"file": f"{name}.png", "kind": "chrome", "label": label, "url": url_note or self.js("location.href"),
                "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    def close(self):
        self.ws.close()
        kill_tree(self.proc.pid)
        time.sleep(1)


def restore_content():
    """Put content/ back into the ConfigMap exactly, the same way deploy.sh first created it."""
    yaml = subprocess.run([KUBECTL, "create", "configmap", "site-content", "-n", "iam624", "--from-file=content/",
                           "--dry-run=client", "-o", "yaml"], cwd=REPO, capture_output=True, check=True).stdout
    subprocess.run([KUBECTL, "replace", "-f", "-"], input=yaml, capture_output=True, check=True)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ip = subprocess.run(["minikube", "-p", PROFILE, "ip"], capture_output=True, text=True, check=True).stdout.strip()
    ns = "-n iam624"
    names = "  ".join(HOSTS)
    h = '$ip = minikube -p exam624 ip; $h = ' + ",".join(f'"--resolve","{x}:80:$ip"' for x in HOSTS)
    pods = ("1..12 | % {{ curl.exe -s @h {url} }} | sls 'pod ([a-z0-9-]+) · node ([a-z0-9-]+)' | "
            "% {{ $_.Matches[0].Groups[1].Value + '  @ ' + $_.Matches[0].Groups[2].Value }} | group -NoElement | ft Count,Name -AutoSize")
    urls = ["http://www.iam-624.com/", "http://www.iam-624.com/photo.jpg", "http://www.iam-624.com/research",
            "http://www.iam-624.com/api-624/hello", "http://www.iam-624.com/api-624/%E0%B8%AA%E0%B8%A7%E0%B8%B1%E0%B8%AA%E0%B8%94%E0%B8%B5",
            "http://www.iam-624.com/api-624", "http://www.id-624.com/", "http://www.id-624.com/research", "http://www.id-624.com/api-624/hello",
            "http://admin.iam-624.com/", "http://admin.iam-624.com/portal", "http://admin.iam-624.com/research"]
    matrix = ("foreach ($u in " + ",".join(f"'{u}'" for u in urls) + ") { curl.exe -s -o NUL -w "
              '"%{http_code}  %{content_type}  %{size_download}B  $u`n" @h $u }')
    only = set(sys.argv[1:])  # e.g. "term-get chrome": redo just these; no argument redoes everything
    meta_path = OUT / "shots.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    shots = [
        ("term-nodes", "minikube profile exam624: 3 nodes", [
            "minikube -p exam624 status", "kubectl get nodes -o wide"]),
        ("term-get", "kubectl get: Deployment, Service, Ingress, ConfigMap and Pods spread over the nodes", [
            f"kubectl get deploy,svc,ingress,configmap {ns}", f"kubectl get pods {ns} -o wide --sort-by=.spec.nodeName"]),
        ("term-describe-ingress", "kubectl describe ingress", [f"kubectl describe ingress {ns}"]),
        ("term-describe-svc", "kubectl describe svc portal-624 and endpoints", [
            f"kubectl describe svc portal-624 {ns}", f"kubectl get endpointslices {ns}"]),
        ("term-describe-deploy", "kubectl describe deployment admin-624 (events left out to fit the window)", [
            f"kubectl describe deploy admin-624 {ns} --show-events=false"]),
        ("term-rbac", "RBAC: ServiceAccount, Role, RoleBinding, kubectl auth can-i", [
            f"kubectl get serviceaccount,role,rolebinding {ns}",
            "foreach ($t in 'get content-reader','patch content-reader','patch content-editor','delete content-editor') "
            "{ $v,$s = $t -split ' '; '{0,-7} {1,-15} -> {2}' -f $v,$s,(kubectl auth can-i $v configmap/site-content -n iam624 "
            "--as=system:serviceaccount:iam624:$s) }"]),
        ("term-curl", "curl tests with the host names mapped to the minikube IP", [h, matrix]),
        ("term-curl-security", "HEAD request, security headers, HTML escaping, no POST on the public host", [
            h, "curl.exe -sI @h http://www.iam-624.com/",
            r"curl.exe -s @h http://www.iam-624.com/api-624/%3Cb%3Ehi%3C%2Fb%3E | sls '<main[^>]*>.*?</main>' | % { $_.Matches.Value }",
            r"curl.exe -s -o NUL -w '%{http_code}\n' @h -X POST -d x http://www.iam-624.com/research"]),
        ("term-linux-hosts", "Linux /etc/hosts on worker node exam624-m02, then plain curl by name (no --resolve)", [
            'minikube -p exam624 ssh -n exam624-m02 -- "head -2 /etc/os-release"',
            f"minikube -p exam624 ssh -n exam624-m02 -- \"grep -q iam-624 /etc/hosts || echo '{ip}  {names}' | sudo tee -a /etc/hosts\"",
            'minikube -p exam624 ssh -n exam624-m02 -- "cat /etc/hosts"',
            "minikube -p exam624 ssh -n exam624-m02 -- \"curl -s http://www.iam-624.com/ | grep -o 'pod portal-624[^<]*'\"",
            "minikube -p exam624 ssh -n exam624-m02 -- \"curl -s http://www.id-624.com/research | grep -o 'pod app-research[^<]*'\"",
            "minikube -p exam624 ssh -n exam624-m02 -- \"curl -s http://admin.iam-624.com/ | grep -o 'pod admin-624[^<]*'\""]),
        ("term-lb", "Load balancing: replies per Pod and node (12 requests each)", [
            h, pods.format(url="http://www.iam-624.com/"), pods.format(url="http://www.iam-624.com/research"),
            pods.format(url="http://www.iam-624.com/api-624/x"), pods.format(url="http://admin.iam-624.com/")]),
    ]
    for name, label, cmds in shots:
        if not only or name in only:
            meta[name] = terminal(name, label, cmds)
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    if only and "chrome" not in only:
        return

    # the "new photo" for the upload demo: the same picture in black and white
    gray = pathlib.Path(tempfile.mkdtemp()) / "photo-bw.jpg"
    Image.open(REPO / "content" / "photo.jpg").convert("L").save(gray, "JPEG", quality=80)
    chrome = Chrome(ip)
    try:
        for name, label, url in [
            ("chrome-portal", "www.iam-624.com : portal-624 shows the photo and name", "http://www.iam-624.com/"),
            ("chrome-id624", "www.id-624.com : the same site through the www.id-624.com name", "http://www.id-624.com/"),
            ("chrome-research", "www.iam-624.com/research : app-research shows the summary", "http://www.iam-624.com/research"),
            ("chrome-api-1", "www.iam-624.com/api-624/สวัสดี K8s : api-624 shows the text big and centred",
             "http://www.iam-624.com/api-624/" + quote("สวัสดี K8s")),
            ("chrome-api-2", "www.iam-624.com/api-624/<b>hi</b> : HTML is escaped", "http://www.iam-624.com/api-624/" + quote("<b>hi</b>", safe="/<>")),
            ("chrome-admin-menu", "admin.iam-624.com : admin-624 menu with two buttons", "http://admin.iam-624.com/"),
        ]:
            chrome.go(url, url.split("//", 1)[1].split("/", 1)[0])
            meta[name] = chrome.shot(name, label)
        # edit the portal: click the first button, type in front of the Thai name, choose the black-and-white photo
        chrome.cmd("Page.bringToFront")
        chrome.js("document.querySelector('a[href=\"/portal\"]').click()")
        chrome.wait_loaded("/portal")
        chrome.js("var t=document.querySelector('input[name=\"name-th\"]'); t.focus(); t.setSelectionRange(0,0)")
        chrome.cmd("Input.insertText", text=MARK)
        chrome.choose_file('input[type="file"]', gray)
        meta["chrome-admin-portal-1"] = chrome.shot("chrome-admin-portal-1", "edit portal: name changed, new photo chosen (not saved yet)")
        chrome.js("document.querySelector('button').click()")
        chrome.wait_loaded("saved=1")
        meta["chrome-admin-portal-2"] = chrome.shot("chrome-admin-portal-2", "after Save: 'บันทึกแล้ว' and the new photo")
        chrome.go("http://www.iam-624.com/")
        meta["chrome-portal-edited"] = chrome.shot("chrome-portal-edited", "www.iam-624.com : new name and photo at once")
        # edit the research summary from the menu's second button
        chrome.go("http://admin.iam-624.com/")
        chrome.js("document.querySelector('a[href=\"/research\"]').click()")
        chrome.wait_loaded("/research")
        chrome.js("var t=document.querySelector('textarea'); t.focus(); t.setSelectionRange(0,0)")
        chrome.cmd("Input.insertText", text=MARK)
        meta["chrome-admin-research-1"] = chrome.shot("chrome-admin-research-1", "edit research: text typed in front of the title")
        chrome.js("document.querySelector('button').click()")
        chrome.wait_loaded("saved=1")
        meta["chrome-admin-research-2"] = chrome.shot("chrome-admin-research-2", "after Save: 'บันทึกแล้ว'")
        chrome.go("http://www.iam-624.com/research")
        meta["chrome-research-edited"] = chrome.shot("chrome-research-edited", "www.iam-624.com/research : the new title at once")
        meta["term-persist"] = terminal("term-persist", "Persistence: delete every portal-624 and app-research Pod, the edit stays", [
            h, f"kubectl delete pod {ns} -l 'app in (portal-624,app-research)'",
            f"kubectl wait {ns} --for=condition=ready pod -l 'app in (portal-624,app-research)' --timeout=120s",
            f"kubectl get pods {ns} -l 'app in (portal-624,app-research)' -o wide",
            "curl.exe -s @h http://www.iam-624.com/ | sls 'admin-edit-\\d+' | select -First 1 | % { 'portal:   ' + $_.Matches.Value }",
            "curl.exe -s @h http://www.iam-624.com/research | sls 'admin-edit-\\d+' | % { 'research: ' + $_.Matches.Value }"])
        chrome.go("http://www.iam-624.com/")
        meta["chrome-portal-restart"] = chrome.shot("chrome-portal-restart", "www.iam-624.com : still edited after the Pods were recreated")
    finally:
        chrome.close()
        restore_content()
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("saved", meta_path)


if __name__ == "__main__":
    main()

