import re, json, io, os

RECON = r'D:\bililive\autoshopkit\recon'
menus_path = os.path.join(RECON, 'resources', 'menus_exe.txt')
text = io.open(menus_path, encoding='utf-8').read()

blocks = []
cur = None
for line in text.splitlines():
    m = re.match(r'^===== MENU id=(\d+) lang=(\d+) len=(\d+) =====$', line)
    if m:
        if cur: blocks.append(cur)
        cur = {'id': int(m.group(1)), 'lang': int(m.group(2)), 'len': int(m.group(3)), 'items': [], 'raw': []}
        continue
    if cur is not None:
        cur['raw'].append(line)

if cur: blocks.append(cur)

# rebuild tree from indentation
item_re = re.compile(r'^(\s*)- id=(\d+) flags=0x([0-9A-Fa-f]+)( \[popup\])? \'(.*)\'$')

def build(raw):
    root = []
    stack = [(-1, root)]
    for line in raw:
        m = item_re.match(line)
        if not m: continue
        depth = len(m.group(1)) // 2
        node = {'id': int(m.group(2)), 'flags': int(m.group(3), 16), 'popup': bool(m.group(4)),
                'text': m.group(5), 'children': []}
        while stack and stack[-1][0] >= depth:
            stack.pop()
        if not stack: stack = [(-1, root)]
        stack[-1][1].append(node)
        stack.append((depth, node['children']))
    return root

for b in blocks:
    b['items'] = build(b['raw'])
    del b['raw']

# command id -> label map (leaf commands only)
cmd = {}
for b in blocks:
    def walk(nodes):
        for n in nodes:
            if not n['popup'] and n['id'] != 0 and n['text']:
                cmd.setdefault(n['id'], n['text'])
            walk(n['children'])
    walk(b['items'])

out = {'menus': blocks, 'commands': cmd}
dst = os.path.join(RECON, 'catalog_menus.json')
io.open(dst, 'w', encoding='utf-8').write(json.dumps(out, ensure_ascii=False, indent=1))
print('menus', len(blocks), 'commands', len(cmd))

kw = ['编译', '转换', '下载', '监控', '仿真', '连接', '在线', '程序', '梯形图', '指令表', 'ST', '变量', '新建', '打开', '保存', '检查', '运行', '停止', '写入']
for k in kw:
    hits = [(i, t) for i, t in cmd.items() if k in t]
    print('---', k, len(hits))
    for i, t in sorted(hits)[:14]:
        print('   ', i, t)
