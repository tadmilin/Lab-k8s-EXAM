# -*- coding: utf-8 -*-
"""Build the two PDFs in docs/ from the repository files and the evidence that collect.py and capture.py saved.

  docs/K8s-EXAM-รายงาน.pdf          design, manifests, files, kubectl commands, get/describe output
  docs/test-service-การทำงาน.pdf    test results and a screenshot of every service

Needs Chrome and `pip install pymupdf`. Run from the repository root: python tools/build_pdf.py
"""
import html
import re
import json
import pathlib
import subprocess
import tempfile

import fitz

REPO = pathlib.Path(__file__).resolve().parent.parent
DOCS, EVID, SHOTS, BUILD = REPO / "docs", REPO / "docs" / "evidence", REPO / "docs" / "screenshots", REPO / "docs" / "build"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
AUTHOR = "Pathomtad Phoovanakulchai"
REPO_URL = "https://github.com/tadmilin/Lab-k8s-EXAM"

CSS = """
@page { size: A4; margin: 14mm 13mm 16mm }
body { font-family: "Leelawadee UI", Tahoma, "Noto Sans Thai", sans-serif; font-size: 10.5pt; line-height: 1.6; color: #1b1f24 }
h1 { font-size: 21pt; margin: 0 0 4pt } h2 { font-size: 14pt; margin: 18pt 0 6pt; padding-bottom: 2pt; border-bottom: 2px solid #2b6cb0; break-after: avoid }
h3 { font-size: 11.5pt; margin: 12pt 0 4pt; break-after: avoid } h4 { font-size: 10pt; margin: 8pt 0 2pt; font-family: Consolas, monospace; break-after: avoid }
p { margin: 4pt 0 } code { font-family: Consolas, monospace; font-size: 9pt; background: #eef2f7; padding: 0 2px }
pre { font-family: Consolas, "Leelawadee UI", monospace; font-size: 7.6pt; line-height: 1.35; background: #f5f7fa; border: 1px solid #d3dae3;
      padding: 5px 8px; margin: 3pt 0 6pt; white-space: pre-wrap; overflow-wrap: anywhere }
table { border-collapse: collapse; width: 100%; margin: 4pt 0 }
td, th { border: 1px solid #c4ccd6; padding: 3px 6px; font-size: 8.8pt; vertical-align: top; text-align: left } th { background: #e6edf5 }
.arch img { width: 100%; border: 1px solid #c4ccd6 }
.fig { break-inside: avoid; margin: 8pt 0 10pt } .fig img { display: block; width: 86%; margin: 0 auto; border: 1px solid #aab } .cap { font-size: 9pt; color: #333; margin-top: 2pt }
.ok { color: #0a7a2f; font-weight: 700 } .bad { color: #b00020; font-weight: 700 } .pb { break-before: page }
.meta td:first-child { width: 28%; background: #eef2f7; font-weight: 600 }
"""


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def pre(text):
    return f"<pre>{html.escape(text.rstrip())}</pre>"


def src(rel, note=""):
    return f"<h4>{rel}</h4>" + (f"<p>{note}</p>" if note else "") + pre(read(rel))


def evidence(name):
    return pre((EVID / name).read_text(encoding="utf-8"))


def tree():
    lines = ["Lab-k8s-EXAM/"]

    def walk(d, prefix):
        items = sorted((p for p in d.iterdir() if p.name not in {".git", "__pycache__", "build"}), key=lambda p: (p.is_file(), p.name))
        for i, p in enumerate(items):
            last = i == len(items) - 1
            lines.append(prefix + ("└── " if last else "├── ") + p.name + ("/" if p.is_dir() else ""))
            if p.is_dir() and p.name not in {"screenshots", "evidence"}:
                walk(p, prefix + ("    " if last else "│   "))
    walk(REPO, "")
    return "\n".join(lines)


def to_pdf(body, title, out):
    BUILD.mkdir(exist_ok=True)
    page = BUILD / (out.stem + ".html")
    page.write_text(f'<!doctype html><html lang="th"><meta charset="utf-8"><title>{html.escape(title)}</title><style>{CSS}</style>{body}</html>',
                    encoding="utf-8")
    with tempfile.TemporaryDirectory() as prof:
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--user-data-dir={prof}",
                        f"--print-to-pdf={out}", page.as_uri()], capture_output=True, timeout=240)
    doc = fitz.open(out)
    doc.set_metadata({"title": title, "author": AUTHOR, "creator": "", "producer": ""})
    for n, pg in enumerate(doc, 1):
        pg.insert_text((pg.rect.width / 2 - 14, pg.rect.height - 22), f"{n} / {len(doc)}", fontsize=8, color=(0.4, 0.4, 0.4))
    tmp = out.with_suffix(".tmp.pdf")
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    tmp.replace(out)
    print(out.name, f"{out.stat().st_size // 1024} KB")


RES = json.loads((EVID / "results.json").read_text(encoding="utf-8"))
OK = all(r["ok"] for r in RES["results"])
PASSED = sum(r["ok"] for r in RES["results"])
SUMMARY = f"ทดสอบ {len(RES['results'])} ข้อ ผ่าน {PASSED} ข้อ"


def results_table():
    rows = "".join(
        f"<tr><td>{r['id']}</td><td>{html.escape(r['desc'])}</td><td>{html.escape(r['url'])}</td><td>{html.escape(r['expected'])}</td>"
        f"<td>{html.escape(r['got'])}</td><td class=\"{'ok' if r['ok'] else 'bad'}\">{'ผ่าน' if r['ok'] else 'ไม่ผ่าน'}</td></tr>" for r in RES["results"])
    return ("<table><tr><th>ข้อ</th><th>ตรวจอะไร</th><th>URL</th><th>ที่คาดหวัง</th><th>ผลจริง</th><th>ผล</th></tr>" + rows + "</table>")


def ingress_version():
    m = re.search(r"ingress-nginx/controller:(v[\d.]+)", read("docs/evidence/00-deploy-output.txt"))
    return m.group(1) if m else "?"


META = f"""<table class="meta">
<tr><td>ผู้จัดทำ</td><td>ปฐมทัศน์ ภูวนกุลชัย ({AUTHOR}) รหัส 68130624</td></tr>
<tr><td>สภาพแวดล้อม</td><td>minikube profile exam624, 3 node (VMware driver), Kubernetes v1.35.1, ingress-nginx controller {ingress_version()}, IP ของ Ingress {RES['ip']}</td></tr>
<tr><td>GitHub</td><td>{REPO_URL}</td></tr>
<tr><td>ผลทดสอบ</td><td class="{'ok' if OK else 'bad'}">{SUMMARY}</td></tr>
</table>"""
NAMES = "www.iam-624.com  admin.iam-624.com  www.id-624.com"


def report():
    wc = {k.strip(): v.strip() for k, v in (l.split(":", 1) for l in read("docs/evidence/wordcount.txt").splitlines() if ":" in l and not l.startswith("#"))}
    steps = [
        ("สร้าง cluster 3 node", "minikube start -p exam624 --nodes 3 --cni=kindnet --driver=vmware --memory=3072 --cpus=2 --disk-size=10g --kubernetes-version=v1.35.1",
         "สร้าง VM สามเครื่อง: exam624 (control-plane), exam624-m02 และ exam624-m03 (worker). kubectl ถูกตั้ง context เป็น exam624 ให้อัตโนมัติ. ใช้ไดรเวอร์อื่นได้ เช่น --driver=docker. "
         "หมายเหตุจากการทำจริง: VM ที่ได้ RAM 2048 MB บูตไม่ขึ้น (ระบบไฟล์ของ minikube ISO อยู่ใน RAM). เครื่องของผู้จัดทำมี RAM ไม่พอสำหรับ 3 x 3072 MB "
         "จึงสร้าง node แรกด้วย --nodes 1 --cni=kindnet --memory=3072 แล้วเพิ่ม worker สองตัวที่ 2560 MB ด้วย minikube node add -p exam624 สองครั้ง. ผลเป็น cluster 3 node เหมือนกัน."),
        ("ตรวจว่ามี 3 node", "kubectl get nodes -o wide", "ทั้งสาม node ต้องอยู่ในสถานะ Ready."),
        ("เปิด Ingress controller", "minikube addons enable ingress -p exam624", "ติดตั้ง ingress-nginx ใน namespace ingress-nginx. controller รันบน node exam624 และรับพอร์ต 80 ที่ IP ของ node นั้น."),
        ("รอ controller พร้อม", "kubectl wait -n ingress-nginx --for=condition=ready pod -l app.kubernetes.io/component=controller --timeout=180s",
         "ถ้า apply Ingress ก่อน controller พร้อม admission webhook จะปฏิเสธ."),
        ("สร้าง resource ทั้งหมด", "kubectl apply -k .",
         "kustomize สร้าง ConfigMap โค้ดสี่ชุดจาก apps/ แล้วสร้าง namespace iam624, ServiceAccount, Role, RoleBinding, Deployment, Service และ Ingress."),
        ("สร้างข้อมูลที่แก้ไขได้ (ครั้งแรกเท่านั้น)", "kubectl create configmap site-content -n iam624 --from-file=content/",
         "ConfigMap site-content เก็บชื่อ รหัส รูป และสรุปงานวิจัย. สร้างครั้งเดียว เพื่อให้ apply ครั้งต่อไปไม่ทับข้อมูลที่แก้จากหน้า admin. deploy.sh ตรวจก่อนว่ามีแล้วหรือยัง."),
        ("รอ Deployment พร้อม", "kubectl wait -n iam624 --for=condition=available deployment --all --timeout=180s", "รอให้ Pod ทั้ง 12 ตัว Ready."),
        ("ดูว่า Pod กระจายไปทุก node", "kubectl get pods -n iam624 -o wide", "คอลัมน์ NODE แสดงว่าแต่ละ Deployment มี Pod หนึ่งตัวบนแต่ละ node."),
        ("เพิ่มชื่อโดเมนใน /etc/hosts", f'echo "$(minikube ip -p exam624)  {NAMES}" | sudo tee -a /etc/hosts',
         "Linux/macOS. บน Windows ใช้ Add-Content กับไฟล์ C:\\Windows\\System32\\drivers\\etc\\hosts ใน PowerShell แบบ Administrator."),
        ("ทดสอบ", "curl http://www.iam-624.com/   และ   curl http://www.iam-624.com/api-624/hello", "หรือเปิด URL ในเบราว์เซอร์. ชุดทดสอบเต็ม: python tools/collect.py"),
        ("แก้โค้ดแล้ว deploy ใหม่", "kubectl apply -k .", "ชื่อ ConfigMap โค้ดเปลี่ยนตามเนื้อหา Deployment จึงทำ rolling update เอง. site-content ไม่ถูกแตะ."),
        ("ลบทั้งหมดเมื่อไม่ใช้", "kubectl delete -k .   แล้ว   minikube delete -p exam624", "ลบ namespace iam624 พร้อมทุก resource รวมถึง site-content แล้วลบ cluster."),
    ]
    hosts_cmd = f"""$ minikube -p exam624 ssh -n exam624-m02 -- "grep -q iam-624 /etc/hosts || echo '{RES['ip']}  {NAMES}' | sudo tee -a /etc/hosts\""""
    steps_html = "".join(f"<h3>ขั้นที่ {i}. {t}</h3><p>{d}</p>{pre('$ ' + c)}" for i, (t, c, d) in enumerate(steps, 1))
    body = f"""
<h1>รายงานการให้บริการด้วย Kubernetes 3 node</h1>
<p>www.iam-624.com, admin.iam-624.com และ www.id-624.com บน minikube</p>
{META}

<h2>1. โจทย์และสิ่งที่สร้าง</h2>
<table><tr><th>URL</th><th>Deployment / Service</th><th>ผลลัพธ์</th></tr>
<tr><td>www.iam-624.com</td><td>portal-624</td><td>รูป ชื่อ ปฐมทัศน์ ภูวนกุลชัย และรหัส 68130624</td></tr>
<tr><td>www.iam-624.com/research</td><td>app-research</td><td>สรุปงานวิจัยที่นำเสนอในวิชาสัมมนา ({wc['words']} คำ)</td></tr>
<tr><td>www.iam-624.com/api-624/&lt;ข้อความ&gt;</td><td>api-624</td><td>แสดง &lt;ข้อความ&gt; ตัวใหญ่กลางจอ</td></tr>
<tr><td>admin.iam-624.com</td><td>admin-624</td><td>หน้าปุ่มสองปุ่ม: แก้ไขข้อมูล Portal (ชื่อ รหัส รูป) และแก้ไขสรุปงานวิจัย</td></tr>
<tr><td>www.id-624.com</td><td>portal-624, app-research, api-624</td><td>ชื่อที่ใช้เข้าถึงระบบตามโจทย์. ใช้ path เดียวกับ www.iam-624.com</td></tr></table>
<p>โจทย์กำหนดให้ระบบทำงานบน Kubernetes 3 node. cluster นี้มี node exam624, exam624-m02 และ exam624-m03. ทุก Deployment มี 3 replica และมี Pod หนึ่งตัวบนแต่ละ node.</p>

<h2>2. การออกแบบ</h2>
<div class="arch"><img src="../architecture.svg"></div>
<p class="cap"><b>ภาพสถาปัตยกรรม.</b> คำขอจากเบราว์เซอร์ไปที่ IP ของ node exam624 พอร์ต 80 (ชื่อโดเมนชี้มาจาก /etc/hosts). Ingress เลือก Service จากชื่อโดเมนและ path. แต่ละ Service ส่งต่อไปยัง Pod สามตัวบนสาม node. portal-624, app-research และ admin-624 อ่านหรือเขียน ConfigMap site-content ผ่าน kube-apiserver ด้วยสิทธิ์จาก RBAC.</p>
<ul>
<li><b>3 node และการกระจาย Pod.</b> ทุก Deployment ตั้ง replicas: 3 และ topologySpreadConstraints บน kubernetes.io/hostname (maxSkew 1, DoNotSchedule). scheduler จึงวาง Pod หนึ่งตัวต่อ node. ถ้า worker node ใดหยุด Pod บนอีกสอง node ยังให้บริการได้. แต่ node exam624 เป็นที่เดียวที่มี control plane (kube-apiserver) และ Ingress controller ถ้า node นี้หยุด ทั้งระบบหยุด.</li>
<li><b>เครือข่ายของ Pod ข้าม node.</b> cluster ใช้ CNI kindnet. แต่ละ node ได้ช่วง IP ของ Pod ของตัวเอง (10.244.0.0/24, 10.244.1.0/24, 10.244.2.0/24) และ kindnet ตั้ง route ระหว่าง node. Ingress controller บน node exam624 จึงส่งคำขอถึง Pod บน worker ได้. ครั้งแรกผู้จัดทำสร้าง cluster แบบ node เดียวแล้วเพิ่ม node ซึ่ง minikube ใช้ bridge CNI ที่ทำงานได้ใน node เดียว จึงสร้างใหม่ด้วย --cni=kindnet.</li>
<li><b>Ingress.</b> Ingress iam624-www มีกฎของ www.iam-624.com และ www.id-624.com: / ไป portal-624, /research ไป app-research, /api-624 ไป api-624. Prefix ที่ยาวที่สุดชนะ. Ingress iam624-admin ส่ง admin.iam-624.com ทั้งหมดไป admin-624.</li>
<li><b>ข้อมูลที่แก้ไขได้อยู่ใน ConfigMap site-content</b> (name-th, name-en, student-id, research.txt และรูป photo.jpg ใน binaryData). Pod อ่านผ่าน Kubernetes API ทุกคำขอ และ admin-624 บันทึกด้วย PATCH. ทุก Pod บนทุก node จึงเห็นข้อมูลใหม่ทันที และข้อมูลอยู่รอดเมื่อ Pod ถูกลบ.</li>
<li><b>ทำไมไม่ใช้ PVC.</b> storage ตั้งต้นของ minikube เป็น hostPath บน node เดียว (ReadWriteOnce). เมื่อ Pod อยู่ต่าง node กัน แต่ละ Pod จะเห็นไฟล์คนละชุด. การ mount ConfigMap เป็น volume ก็ใช้ไม่ได้ดี เพราะ kubelet อัปเดตไฟล์ช้าได้ถึงประมาณ 1 นาที.</li>
<li><b>RBAC สิทธิ์น้อยที่สุด.</b> ServiceAccount content-reader (portal-624, app-research) ทำได้แค่ get และ content-editor (admin-624) ทำได้ get และ patch. ทั้งสอง Role จำกัดด้วย resourceNames ให้ใช้ได้กับ site-content เท่านั้น. api-624 ไม่มี token ของ API เลย (automountServiceAccountToken: false).</li>
<li><b>ไม่ต้อง build image.</b> ทุก Pod ใช้ python:3.12-alpine และ mount โค้ดจาก ConfigMap ที่ kustomize สร้างจาก apps/. โค้ดใช้ Python standard library อย่างเดียว.</li>
<li><b>ความปลอดภัยเบื้องต้น.</b> Pod ไม่รันเป็น root, root filesystem อ่านอย่างเดียว, ไม่มี Linux capability. ข้อความจาก URL และจากฟอร์มถูก HTML-escape. ทุกหน้าส่ง Content-Security-Policy. หน้า admin ตรวจข้อมูลก่อนบันทึก: ทุกช่องต้องไม่ว่าง ยาวไม่เกิน 120 ตัวอักษร และรูปต้องเป็น JPEG ไม่เกิน 600 KB. host www ส่ง POST ไม่ได้.</li>
<li><b>ข้อจำกัด.</b> portal-624 และ app-research อ่าน site-content จาก kube-apiserver ทุกคำขอ จึงขึ้นกับ control plane บน node exam624 (lab นี้มี control plane ตัวเดียว). หน้า admin ยังไม่มีการล็อกอินตามขอบเขตของโจทย์. ถ้าใช้งานจริงควรเพิ่ม authentication เช่น basic auth ของ ingress-nginx หรือ OAuth และใช้ HTTPS.</li></ul>

<h2>3. โครงสร้างไฟล์</h2>
{pre(tree())}

<h2>4. ไฟล์ hosts</h2>
<p>ชื่อ iam-624.com และ id-624.com ไม่มีใน DNS จริง. ไฟล์ hosts ของเครื่องที่เปิดเบราว์เซอร์ต้องชี้ทั้งสามชื่อไปที่ IP ของ node exam624 ซึ่ง Ingress controller รับพอร์ต 80. Ingress เลือก backend จากหัว Host ของคำขอ.</p>
{src('hosts.txt')}
<p>ใน lab นี้ IP คือ {RES['ip']}. ภาพหน้าจอ Chrome และผลตรวจบน Windows ใช้ <code>curl --resolve</code> และ Chrome ที่ตั้ง <code>--host-resolver-rules</code> ให้สามชื่อชี้ไปที่ IP นี้. ผลเหมือนกับการแก้ไฟล์ hosts เพราะคำขอที่ถึง Ingress เหมือนกันทุกประการ.</p>
<h3>ทดสอบด้วย /etc/hosts ของ Linux จริง</h3>
<p>node ของ minikube เป็น Linux VM. ผู้จัดทำเพิ่มบรรทัดจาก hosts.txt ลงใน /etc/hosts ของ worker node exam624-m02 ด้วย <code>minikube ssh</code> แล้วใช้ curl เรียกด้วยชื่อโดเมนตรง ๆ โดยไม่ใช้ --resolve. คำขอจาก m02 วิ่งข้ามเครือข่ายไปที่ Ingress บน node exam624. ไฟล์ /etc/hosts ของ VM กลับเป็นค่าเดิมเมื่อ VM รีสตาร์ต.</p>
{pre(hosts_cmd)}
{evidence('06-linux-hosts.txt')}

<h2 class="pb">5. Kubernetes manifest</h2>
<p>kustomization.yaml รวม manifest ทุกไฟล์และสร้าง ConfigMap โค้ดสี่ชุด: portal-code, research-code, api-code, admin-code. ไฟล์ Deployment ทั้งสี่มีโครงเดียวกัน ต่างกันที่ชื่อ, ConfigMap โค้ด และ ServiceAccount.</p>
{src('kustomization.yaml')}{src('k8s/namespace.yaml')}{src('k8s/rbac.yaml')}{src('k8s/portal-624.yaml')}{src('k8s/app-research.yaml')}{src('k8s/api-624.yaml')}{src('k8s/admin-624.yaml')}{src('k8s/ingress.yaml')}
<h4>ConfigMap site-content</h4>
<p>สร้างจากไฟล์ในโฟลเดอร์ content/ ด้วยคำสั่งด้านล่าง (ขั้นที่ 6). ไฟล์ที่เป็นข้อความเข้า data และ photo.jpg เข้า binaryData.</p>
{pre('$ kubectl create configmap site-content -n iam624 --from-file=content/')}
{pre('content/name-th      ' + read('content/name-th') + chr(10) + 'content/name-en      ' + read('content/name-en') + chr(10) + 'content/student-id   ' + read('content/student-id') + chr(10) + 'content/photo.jpg    รูปผู้จัดทำ (JPEG ' + str((REPO / 'content/photo.jpg').stat().st_size // 1024) + ' KB)' + chr(10) + 'content/research.txt สรุปงานวิจัย (หัวข้อ 10)')}

<h2 class="pb">6. โค้ดของบริการ</h2>
<p>ใช้ Python standard library อย่างเดียว. common.py ใช้ร่วมกันทั้งสี่บริการ: แม่แบบหน้าเว็บ, header ความปลอดภัย, HTTP server และฟังก์ชันอ่าน/บันทึก site-content ผ่าน Kubernetes API.</p>
{src('apps/common.py')}{src('apps/portal/app.py', 'ส่งหน้าแรกและรูป /photo.jpg จาก site-content.')}{src('apps/research/app.py', 'ส่งหน้า /research จาก site-content.')}{src('apps/api/app.py', 'แสดงข้อความหลัง /api-624/ ตัวใหญ่กลางจอ.')}{src('apps/admin/app.py', 'เมนูสองปุ่ม, ฟอร์มแก้ไข Portal และ Research, ตรวจข้อมูล แล้ว PATCH site-content.')}
{src('deploy.sh', 'สคริปต์ deploy สำหรับ Linux/macOS (ขั้นที่ 1 ถึง 9 ด้านล่าง). บน Windows ใช้ deploy.cmd ซึ่งทำงานเหมือนกัน.')}

<h2 class="pb">7. ขั้นตอนสั่งการ kubectl</h2>
<p>รันที่ root ของ repository. ผลที่ได้จริงของการ deploy อยู่ท้ายหัวข้อนี้.</p>
{steps_html}
<h3>ผลจริงของการ deploy</h3>
<p>ผลนี้มาจากการ deploy ครั้งแรก. หลังจากนั้นผู้จัดทำแก้โค้ดและ apply อีกสามครั้ง ชื่อ ConfigMap โค้ด (ส่วน hash ท้ายชื่อ) และชื่อ Pod ในหัวข้อ 8 จึงต่างจากผลนี้.</p>
{evidence('00-deploy-output.txt')}

<h2 class="pb">8. การตรวจสอบด้วย kubectl get และ describe</h2>
<h3>8.1 Cluster 3 node และ Ingress controller</h3>{evidence('01-cluster.txt')}
<h3>8.2 kubectl get</h3><p>คอลัมน์ NODE ของ Pod แสดงว่าแต่ละ Deployment มี Pod บนทั้งสาม node.</p>{evidence('02-get.txt')}
<h3>8.3 kubectl describe ingress</h3>{evidence('03-describe-ingress.txt')}
<h3>8.4 kubectl describe service, deployment, configmap</h3>{evidence('04-describe-workload.txt')}
<h3>8.5 RBAC</h3>{evidence('07-rbac.txt')}
<h3>8.6 Log ของ Pod</h3><p>เวลาใน log ของ Pod เป็นเวลา UTC (เวลาไทยลบ 7 ชั่วโมง).</p>{evidence('05-logs.txt')}

<h2 class="pb">9. ผลการทดสอบ</h2>
<p class="{'ok' if OK else 'bad'}">{SUMMARY}. ภาพหน้าจอของทุกบริการอยู่ในไฟล์ test-service-การทำงาน.pdf.</p>
{results_table()}

<h2>10. เนื้อหาสรุปงานวิจัย</h2>
<p>หน้า /research แสดงสรุปงานวิจัยเรื่อง “การพัฒนาระบบคิวเพื่อจัดการการใช้ Unity Editor ร่วมกันของ AI หลายเอเจนต์” ที่ผู้จัดทำนำเสนอในวิชาสัมมนา. ผู้จัดทำเขียนสรุปจากสไลด์นำเสนอและร่างบทความของงานวิจัยนี้.</p>
<p>จำนวนคำ: <b>{wc['words']} คำ</b> (เกณฑ์ 300 ถึง 500 คำ). วิธีนับ: {html.escape(wc['method'])}. ภาษาไทยไม่เว้นวรรคระหว่างคำ ตัวเลขจึงขึ้นกับตัวตัดคำ.</p>
{src('content/research.txt')}
"""
    to_pdf(body, "รายงาน Kubernetes 3 node iam-624", DOCS / "K8s-EXAM-รายงาน.pdf")


CAP = {
    "chrome-portal": ("www.iam-624.com ทำงานด้วย portal-624", "แสดงรูป ชื่อ ปฐมทัศน์ ภูวนกุลชัย และรหัส 68130624. Footer บอกชื่อ Pod และ node ที่ตอบ."),
    "chrome-id624": ("www.id-624.com", "เข้าระบบด้วยชื่อ www.id-624.com ได้หน้าเดียวกัน (portal-624)."),
    "chrome-research": ("www.iam-624.com/research ทำงานด้วย app-research", "แสดงสรุปงานวิจัยที่นำเสนอในวิชาสัมมนา."),
    "chrome-api-1": ("www.iam-624.com/api-624/สวัสดี K8s ทำงานด้วย api-624", "ข้อความใน URL แสดงตัวใหญ่กลางจอ. ภาษาไทยและช่องว่างแสดงถูกต้อง."),
    "chrome-api-2": ("การทดสอบความปลอดภัย: /api-624/&lt;b&gt;hi&lt;/b&gt;",
                     "ภาพนี้ตั้งใจส่งแท็ก HTML ไปใน URL เพื่อทดสอบช่องโหว่ XSS. หน้าแสดงข้อความ &lt;b&gt;hi&lt;/b&gt; ตรงตามที่ส่ง ไม่แปลงเป็นแท็ก. "
                     "ถ้าระบบแปลงแท็กได้ คนอื่นก็ส่งลิงก์ที่ฝัง &lt;script&gt; ให้รันในเบราว์เซอร์ของผู้เปิดได้."),
    "chrome-admin-menu": ("admin.iam-624.com ทำงานด้วย admin-624", "หน้าปุ่มสองปุ่มสำหรับเลือกแก้ไขข้อมูลของ Portal หรือของ Research."),
    "chrome-admin-portal-1": ("กดปุ่ม “แก้ไขข้อมูล Portal”", "ฟอร์มแสดงข้อมูลปัจจุบัน. พิมพ์ [admin-edit-8421] หน้าชื่อ และเลือกรูปใหม่ (รูปเดิมแบบขาวดำ). ยังไม่กดบันทึก."),
    "chrome-admin-portal-2": ("กดบันทึกข้อมูล Portal", "หน้าแสดง “บันทึกแล้ว”. รูปปัจจุบันในฟอร์มเปลี่ยนเป็นรูปใหม่."),
    "chrome-portal-edited": ("ผลที่ www.iam-624.com", "ชื่อใหม่และรูปใหม่แสดงทันที."),
    "chrome-admin-research-1": ("กดปุ่ม “แก้ไขสรุปงานวิจัย”", "พิมพ์ [admin-edit-8421] หน้าหัวข้อ. ยังไม่กดบันทึก."),
    "chrome-admin-research-2": ("กดบันทึกสรุปงานวิจัย", "หน้าแสดง “บันทึกแล้ว”."),
    "chrome-research-edited": ("ผลที่ www.iam-624.com/research", "หัวข้อใหม่แสดงทันที."),
    "term-persist": ("ลบ Pod แล้วข้อมูลยังอยู่", "ลบ Pod ของ portal-624 และ app-research ทั้งหกตัว. Deployment สร้าง Pod ใหม่บนทั้งสาม node. curl ยังพบข้อความที่แก้ทั้งสองหน้า เพราะข้อมูลอยู่ใน ConfigMap site-content ไม่ได้อยู่ใน Pod."),
    "chrome-portal-restart": ("www.iam-624.com หลังสร้าง Pod ใหม่", "Footer แสดงชื่อ Pod ใหม่. ชื่อและรูปที่แก้ยังอยู่. หลังถ่ายภาพ ข้อมูลถูกคืนค่าเดิมจาก content/."),
    "term-nodes": ("cluster 3 node", "minikube status และ kubectl get nodes: node exam624 (control-plane), exam624-m02 และ exam624-m03 อยู่ในสถานะ Ready."),
    "term-get": ("kubectl get", "Deployment ทั้งสี่พร้อม 3/3. คอลัมน์ NODE ของ Pod แสดงว่าแต่ละ Deployment มี Pod บนทุก node."),
    "term-describe-ingress": ("kubectl describe ingress", "กฎ host และ path ของ iam624-www (www.iam-624.com, www.id-624.com) และ iam624-admin พร้อม backend ของแต่ละ path."),
    "term-describe-svc": ("kubectl describe svc และ endpointslices", "Service portal-624 มี endpoint สามตัวจากสาม node. ทุก Service มี endpoint สามตัว."),
    "term-describe-deploy": ("kubectl describe deployment admin-624", "replicas 3/3, Service Account content-editor, readiness probe, ตัวแปร NODE_NAME, volume ของโค้ด, topology spread constraint และ ReplicaSet ปัจจุบัน. ใช้ --show-events=false เพื่อให้ผลพอดีหน้าต่าง (events ของ rolling update อยู่ในหัวข้อ 8.4 ของรายงาน)."),
    "term-rbac": ("RBAC", "ServiceAccount, Role และ RoleBinding. kubectl auth can-i ยืนยันว่า content-reader อ่านได้แต่แก้ไม่ได้ และ content-editor แก้ได้แต่ลบไม่ได้."),
    "term-curl": ("ผลตอบกลับของทุก URL", "รหัส HTTP, ชนิดเนื้อหา และขนาด. คำขอใช้ --resolve ให้ชื่อโดเมนชี้ไปที่ IP ของ Ingress."),
    "term-curl-security": ("HEAD, header ความปลอดภัย, การ escape HTML", "HEAD ได้ 200 พร้อม Content-Security-Policy และ X-Content-Type-Options. &lt;b&gt; ถูกแปลงเป็น &amp;lt;b&amp;gt;. POST ไปที่ host www ได้ 501 (แก้ข้อมูลได้เฉพาะทาง admin.iam-624.com)."),
    "term-linux-hosts": ("/etc/hosts ของ Linux (worker node exam624-m02)", "เพิ่มบรรทัด hosts แล้ว curl ด้วยชื่อโดเมนตรง ๆ โดยไม่ใช้ --resolve. ทั้งสามชื่อตอบจาก Pod ที่ถูกต้อง."),
    "term-lb": ("การกระจายคำขอไปยัง Pod และ node", "ส่งคำขอ 12 ครั้งต่อบริการ. Pod ทั้งสามตัวบนสาม node ได้รับคำขอ. Count คือจำนวนครั้งที่แต่ละ Pod ตอบ."),
}
GROUPS = [
    ("1. portal-624 (www.iam-624.com และ www.id-624.com)", ["chrome-portal", "chrome-id624"]),
    ("2. app-research", ["chrome-research"]), ("3. api-624", ["chrome-api-1", "chrome-api-2"]),
    ("4. admin-624: หน้าปุ่ม", ["chrome-admin-menu"]),
    ("5. admin-624: แก้ไขข้อมูล Portal", ["chrome-admin-portal-1", "chrome-admin-portal-2", "chrome-portal-edited"]),
    ("6. admin-624: แก้ไขสรุปงานวิจัย", ["chrome-admin-research-1", "chrome-admin-research-2", "chrome-research-edited"]),
    ("7. ข้อมูลอยู่รอดเมื่อ Pod ถูกลบ", ["term-persist", "chrome-portal-restart"]),
    ("8. cluster 3 node, kubectl get และ describe", ["term-nodes", "term-get", "term-describe-ingress", "term-describe-svc", "term-describe-deploy", "term-rbac"]),
    ("9. curl, /etc/hosts ของ Linux และการกระจายคำขอ", ["term-curl", "term-curl-security", "term-linux-hosts", "term-lb"]),
]


def test_evidence():
    meta = json.loads((SHOTS / "shots.json").read_text(encoding="utf-8"))
    figs, n = "", 0
    for title, names in GROUPS:
        figs += f"<h2>{title}</h2>"
        for name in names:
            n += 1
            head, text = CAP[name]
            figs += (f'<div class="fig"><img src="../screenshots/{meta[name]["file"]}"><div class="cap"><b>ภาพที่ {n}. {head}</b> '
                     f'{text} <i>({meta[name]["time"]})</i></div></div>')
    body = f"""
<h1>ไฟล์ตรวจสอบการทดสอบการทำงาน</h1>
<p>ภาพหน้าจอของทุก service: iam-624 บน Kubernetes 3 node</p>
{META}
<table class="meta"><tr><td>วิธีถ่ายภาพ</td><td>ภาพเป็นหน้าต่างจริงของ Chrome และ PowerShell ที่ถ่ายด้วย PrintWindow (ไม่ใช่ภาพทั้งหน้าจอ). Chrome ตั้ง host-resolver-rules ให้ {NAMES} ชี้ไปที่ {RES['ip']} ซึ่งมีผลเท่ากับไฟล์ hosts. Chrome ถูกควบคุมผ่าน DevTools ตอนกดปุ่ม พิมพ์ เลือกไฟล์รูป และกดบันทึก.</td></tr></table>
<h2>ผลการทดสอบอัตโนมัติ</h2>
{results_table()}
<p>หลังทดสอบ ข้อมูลใน site-content ถูกคืนเป็นค่าเดิมจากโฟลเดอร์ content/ ทุกครั้ง (ภาพที่ 7 ถึง 14 ใช้ข้อความ [admin-edit-8421] และรูปขาวดำชั่วคราว).</p>
{figs}"""
    to_pdf(body, "ไฟล์ตรวจสอบการทดสอบ iam-624", DOCS / "test-service-การทำงาน.pdf")


if __name__ == "__main__":
    report()
    test_evidence()

