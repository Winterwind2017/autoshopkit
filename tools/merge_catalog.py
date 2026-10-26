import json, io, os, re

RECON = r'D:\bililive\autoshopkit\recon'
RES = os.path.join(RECON, 'resources')

def load_lines(p):
    return io.open(p, encoding='utf-8').read().splitlines()

# menus
cat = json.loads(io.open(os.path.join(RECON, 'catalog_menus.json'), encoding='utf-8').read())
menus = cat['menus']

# string table hints
hints = {}
for line in load_lines(os.path.join(RES, 'strtab_exe.txt')):
    p = line.split('\t', 1)
    if len(p) == 2 and p[0].isdigit():
        hints[int(p[0])] = p[1]

# accelerators
accel = {}
for line in load_lines(os.path.join(RES, 'accelerators.txt')):
    m = re.match(r'\s*cmd=(\d+) key=(.*?) mods=(\S*)', line)
    if m:
        accel.setdefault(int(m.group(1)), []).append((m.group(3) + '+' + m.group(2)).strip('+'))

# toolbars
toolbars = []
for line in load_lines(os.path.join(RES, 'accelerators.txt')):
    pass
# parse toolbar ids from a saved text? re-derive from earlier: store manually via resource dump file if exists
tb_file = os.path.join(RES, 'toolbars.json')
if os.path.exists(tb_file):
    toolbars = json.loads(io.open(tb_file, encoding='utf-8').read())

# merge labels: menus label wins, then hint
label = {}
for m in menus:
    def walk(nodes):
        for n in nodes:
            if not n['popup'] and n['id'] and n['text']:
                label.setdefault(n['id'], n['text'])
            walk(n['children'])
    walk(m['items'])

merged = {}
for i in set(list(label) + list(hints) + list(accel)):
    merged[i] = {
        'label': label.get(i, ''),
        'hint': hints.get(i, ''),
        'keys': accel.get(i, []),
    }

out = os.path.join(RECON, 'catalog_commands.json')
io.open(out, 'w', encoding='utf-8').write(json.dumps({'commands': merged, 'menus': menus}, ensure_ascii=False, indent=1))
print('labels', len(label), 'hints', len(hints), 'keys', len(accel), 'merged', len(merged))

# print interesting
def show(name, pred, limit=40):
    rows = [(i, v) for i, v in merged.items() if pred(i, v)]
    rows.sort()
    print('====', name, len(rows))
    for i, v in rows[:limit]:
        print('  %6d  %-28s | %-40s | %s' % (i, v['label'], v['hint'][:40], ','.join(v['keys'])))

show('compile', lambda i, v: '编译' in v['hint'] or '编译' in v['label'])
show('download', lambda i, v: '下载' in v['hint'] or '下载' in v['label'])
show('monitor', lambda i, v: '监控' in v['hint'] or '监控' in v['label'] or '监视' in v['hint'])
show('run/stop', lambda i, v: ('运行' in v['hint'] or '停止' in v['hint']) and len(v['hint']) < 40)
show('program', lambda i, v: '程序' in v['label'])
