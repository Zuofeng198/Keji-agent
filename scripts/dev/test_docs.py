import urllib.request, json, sys, glob
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

r = urllib.request.urlopen('http://127.0.0.1:8000/health')
print('OK:', r.read().decode())

query = '帮我生成10个word文档，内容是姓名、性别、年龄，随机生成，保存到D:/zhuomian/yuangong/'
data = json.dumps({'query': query}).encode()
req = urllib.request.Request('http://127.0.0.1:8000/chat', data=data,
    headers={'Content-Type': 'application/json'}, method='POST')
resp = urllib.request.urlopen(req, timeout=300)
r = json.loads(resp.read().decode())
print('回复:', r['reply'][:200])

files = sorted(glob.glob('D:/zhuomian/yuangong/*.docx'))
print('文件:', len(files))
if files:
    from docx import Document
    texts = []
    for f in files[:5]:
        doc = Document(f)
        t = '|'.join(p.text.strip() for p in doc.paragraphs if p.text.strip())
        texts.append(t)
        print(' ', f.split('\\')[-1], ':', t[:50])
    print('唯一:', len(set(texts)), '/', len(texts))
