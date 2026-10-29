"""从已记录的固定uv隔离生成物提取入口PE模板；不重装、不执行入口。"""
import configparser, hashlib, io, json, struct, zipfile, zlib
from pathlib import Path

WORK = Path(__file__).parent
CONTROL = Path(r'E:\NTRegCtrl\a5-20261029-ctrl1\g0000000000000000')
INDEX = WORK / 'gui-cp310-installed-files-v1.json'

def u32(b, at): return struct.unpack_from('<I', b, at)[0]
def put(b, at, value): struct.pack_into('<I', b, at, value)
def aligned(n, a): return (n+a-1)//a*a
def padding(n): return (b'PADDINGXXPADDING'*(n//16+1))[:n]

def archive(main):
    name = b'__main__.py'; n = len(main); crc = zlib.crc32(main)
    local = struct.pack('<IHHHHHIIIHH', 0x04034b50, 10, 2048, 0, 0, 33, crc, n, n, len(name), 0)+name+main
    central = struct.pack('<IHHHHHHIIIHHHHHII', 0x02014b50, 831, 10, 2048, 0, 0, 33, crc, n, n, len(name), 0, 0, 0, 0, 0, 0)+name
    return local+central+struct.pack('<IHHHHIIH', 0x06054b50, 0, 0, 1, 1, len(central), len(local), 0)

def reconstruct(template, python_path, main, kind):
    # 固定uv0.11.16 PE布局；只允许四项资源内容与由其长度推导的字段变化。
    start = 43008; old_raw = u32(template, 640)
    output = bytearray(template[:start]); resource = bytearray(template[start:start+356])
    manifest_start = u32(template, start+240)-61440
    manifest_size = u32(template, start+244)
    manifest = template[start+manifest_start:start+manifest_start+manifest_size]
    payloads = [python_path.encode(), archive(main), bytes([kind]), manifest]
    for entry, payload in zip((192,208,224,240), payloads):
        resource += padding(aligned(len(resource), 4)-len(resource))
        put(resource, entry, 61440+len(resource)); put(resource, entry+4, len(payload))
        resource += payload
    resource += padding(aligned(len(resource),4)-len(resource))
    if len(resource)>4096: raise ValueError('resource region exceeds fixed section virtual closure')
    new_raw = aligned(len(resource),512)
    put(output, 152, u32(template,152)+new_raw-old_raw)
    put(output, 276, len(resource)); put(output, 632, len(resource)); put(output, 640, new_raw)
    put(output, 684, start+new_raw)
    return bytes(output)+bytes(resource)+padding(new_raw-len(resource))+template[start+old_raw:]

def main():
    raw = INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='3e0c861b6b4c7e2b9a1a5615193cca976a194e72100aaa1afc54a39065d8bea8':
        raise ValueError('input identity differs')
    index=json.loads(raw); entries=[]; seen=set()
    template=(CONTROL/'Scripts/cffi-gen-src.exe').read_bytes()
    if hashlib.sha256(template).hexdigest()!='159fbd3f813f417e5718fd8ecaf7a4973925b7b4dca08815f2f225bd06f47632':
        raise ValueError('fixed isolated uv generated PE template identity differs')
    # 样本身份由先前固定uv+确定synthetic wheel的生成日志和所有资源重建共同核对。
    for package in index['packages']:
        parser=configparser.ConfigParser(interpolation=None); parser.optionxform=str
        parser.read_string(package['entry_points'] or '')
        for section in ('console_scripts','gui_scripts'):
            items=list(parser.items(section)) if parser.has_section(section) else []
            if package['name']=='pip' and section=='console_scripts':
                target=dict(items).get('pip')
                if target: items.append(('pip3.10',target))
            for name,target in items:
                if name.lower() in seen: raise ValueError('entrypoint alias')
                seen.add(name.lower()); path='Scripts/'+name+'.exe'; data=(CONTROL/path).read_bytes()
                start=u32(data,43008+208)-61440+43008; size=u32(data,43008+212)
                zipped=data[start:start+size]
                with zipfile.ZipFile(io.BytesIO(zipped)) as source:
                    if source.namelist()!=['__main__.py']: raise ValueError('unexpected archive member')
                    script=source.read('__main__.py')
                if archive(script)!=zipped: raise ValueError('zip envelope differs')
                python=str(CONTROL/'Scripts/python.exe')
                text=script.decode(); prefix='#!'+python+'\n'
                if not text.startswith(prefix): raise ValueError('script python path differs')
                script_template='#!{{PYTHON}}\n'+text[len(prefix):]
                kind=1 if section=='console_scripts' else 2
                expected=reconstruct(template,python,script,kind)
                if data!=expected: raise ValueError('PE reconstruction differs: '+name)
                entries.append({'package':package['name'],'path':path,'target':target,'kind':kind,'script_template':script_template})
    index['entrypoint_controls']=sorted(entries,key=lambda x:x['path'].lower())
    index['entrypoint_pe_template_hex']=template.hex()
    index['controlled_entrypoint_fixture']={'wheel_sha256':hashlib.sha256((WORK/'nt_registration_control-0.0.1-py3-none-any.whl').read_bytes()).hexdigest(),
        'source':'fixed uv offline generated from fully specified synthetic wheel; every PE byte reconstructed; no GUI dependency or entrypoint executed',
        'template_sha256':hashlib.sha256(template).hexdigest()}
    encoded=(json.dumps(index,ensure_ascii=False,separators=(',',':'),sort_keys=True)+'\n').encode()
    path=WORK/'gui-cp310-installed-files-v2.json'
    with path.open('xb') as output: output.write(encoded)
    print(json.dumps({'path':str(path),'bytes':len(encoded),'sha256':hashlib.sha256(encoded).hexdigest(),'entrypoints':len(entries)}))

if __name__=='__main__': main()
