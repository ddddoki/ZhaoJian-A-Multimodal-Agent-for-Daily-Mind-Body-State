"""Private photo and expressive journal, including explicit, optional model requests."""
import base64
import binascii
from datetime import datetime, timezone
from io import BytesIO
import json
from uuid import UUID, uuid4

FIELDS = "id,created,updated,revision,state,words,story,context,need,caption,width,height,reflection,reflection_source,scene,scene_source"
MAX_BYTES = 5 * 1024 * 1024
PAGE_SIZE = 16


def init(db):
    db.executescript("""
        CREATE TABLE IF NOT EXISTS journal_entries(
            seq INTEGER PRIMARY KEY, id TEXT NOT NULL UNIQUE, owner INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created TEXT NOT NULL, updated TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
            state TEXT NOT NULL, words TEXT NOT NULL, story TEXT NOT NULL, context TEXT NOT NULL, need TEXT NOT NULL,
            caption TEXT NOT NULL, image_b64 TEXT NOT NULL DEFAULT '', width INTEGER NOT NULL DEFAULT 0, height INTEGER NOT NULL DEFAULT 0,
            reflection TEXT NOT NULL DEFAULT '', reflection_source TEXT NOT NULL DEFAULT '',
            scene TEXT NOT NULL DEFAULT '', scene_source TEXT NOT NULL DEFAULT '');
        CREATE INDEX IF NOT EXISTS journal_owner_seq ON journal_entries(owner,seq DESC);
    """)


def clean(value, limit, label):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'{label}最多 {limit} 字')
    return value.strip()


def when():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def entry_id(value):
    try:
        return UUID(value).hex
    except (ValueError, TypeError, AttributeError):
        raise ValueError('这篇手记不存在或已删除') from None


def owned(db, owner, key, fields=FIELDS):
    row = db.execute(f'SELECT {fields} FROM journal_entries WHERE owner=? AND id=?', (owner, entry_id(key))).fetchone()
    if row is None:
        raise ValueError('这篇手记不存在或已删除')
    return row


def summary(row):
    item = dict(row)
    item['words'] = json.loads(item['words'])
    return item


def decode_image(encoded):
    try:
        from PIL import Image, ImageOps, UnidentifiedImageError
    except ImportError:
        raise ValueError('照片组件尚未安装，请在项目目录运行 python -m pip install -r requirements.txt') from None
    if not isinstance(encoded, str) or not encoded or len(encoded) > 4 * ((MAX_BYTES + 2) // 3):
        raise ValueError('照片请控制在 5 MB 以内')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw)>MAX_BYTES:
            raise ValueError('照片请控制在 5 MB 以内')
        with Image.open(BytesIO(raw), formats=('JPEG', 'PNG', 'WEBP')) as source:
            if source.width * source.height > 16_000_000 or source.width > 10000 or source.height > 10000:
                raise ValueError('请缩小照片尺寸后再上传')
            if getattr(source, 'n_frames', 1) != 1:
                raise ValueError('请选择单张静态照片')
            source.load()
            pixels = ImageOps.exif_transpose(source)
            pixels.thumbnail((1440,1440), Image.Resampling.LANCZOS)
            if pixels.mode == 'RGBA' or 'transparency' in pixels.info:
                rgba = pixels.convert('RGBA')
                canvas = Image.new('RGB', rgba.size, 'white')
                canvas.paste(rgba, mask=rgba.getchannel('A'))
            else:
                canvas = pixels.convert('RGB')
            # Re-encode the pixels only. No EXIF, GPS, filename, thumbnail or metadata enters the database.
            out = BytesIO()
            canvas.save(out, format='JPEG', quality=87, optimize=True)
            return base64.b64encode(out.getvalue()).decode('ascii'), canvas.width, canvas.height
    except (binascii.Error, UnidentifiedImageError, OSError, Image.DecompressionBombError, SyntaxError, OverflowError):
        raise ValueError('图片无法读取，请选择完整的 JPG、PNG 或 WebP 照片') from None


def checked_revision(data):
    value = data.get('revision')
    if type(value) is not int or value < 1:
        raise ValueError('请重新打开手记，再保存修改')
    return value


def save(db, owner, data):
    story=clean(data.get('story',''), 4000, '感受')
    context=clean(data.get('context',''), 160, '场景')
    need=clean(data.get('need',''), 160, '当下需要')
    caption=clean(data.get('caption',''), 240, '照片说明')
    state=data.get('state','published')
    words=data.get('words',[])
    if not isinstance(words,list) or len(words)>6 or any(not isinstance(w,str) or not w.strip() or len(w)>20 for w in words):
        raise ValueError('最多选择 6 个感受词，每个最多 20 字')
    words=list(dict.fromkeys(w.strip() for w in words))
    if state not in ('draft','published'):
        raise ValueError('保存状态无效')
    replacement=None
    if 'image' in data:
        replacement = ('',0,0) if data['image'] is None else decode_image(data['image'])
    now=when()
    if not db.in_transaction:
        db.execute('BEGIN IMMEDIATE')
    key=entry_id(data['id']) if 'id' in data else None
    prior=owned(db, owner, key) if key is not None else None
    revision=checked_revision(data) if prior else 0
    if prior and prior['revision'] != revision:
        raise ValueError('这篇手记刚被更新，请重新打开再修改')
    contains_image = bool(replacement[1]) if replacement is not None else bool(prior and prior['width'])
    if not (story or words or contains_image or need or context):
        raise ValueError('写一句、选一个感受词，或放入一张照片后再保存')
    if not contains_image:
        caption=''
    fields=(now,state,json.dumps(words,ensure_ascii=False),story,context,need,caption)
    if prior:
        changed_text=any(prior[k]!=v for k,v in zip(('words','story','context','need'),fields[2:6]))
        changed_image=replacement is not None or caption!=prior['caption']
        db.execute("""UPDATE journal_entries SET updated=?,state=?,words=?,story=?,context=?,need=?,caption=?,revision=revision+1,
          reflection=CASE WHEN ? THEN '' ELSE reflection END, reflection_source=CASE WHEN ? THEN '' ELSE reflection_source END,
          scene=CASE WHEN ? THEN '' ELSE scene END, scene_source=CASE WHEN ? THEN '' ELSE scene_source END
          WHERE owner=? AND id=?""", (*fields,changed_text,changed_text,changed_image,changed_image,owner,key))
    else:
        key=uuid4().hex
        db.execute("""INSERT INTO journal_entries(id,owner,created,updated,state,words,story,context,need,caption)
                      VALUES(?,?,?,?,?,?,?,?,?,?)""",(key,owner,now,*fields))
    if replacement is not None:
        db.execute('UPDATE journal_entries SET image_b64=?,width=?,height=? WHERE owner=? AND id=?',(*replacement,owner,key))
    return summary(owned(db,owner,key))


def handle(db,user,method,path,data):
    if path!='/api/journal' and not path.startswith('/api/journal/'):
        return NotImplemented
    if user['role']!='student':
        raise PermissionError('心情手记仅本人可访问')
    owner=user['id']
    if (method=='GET' and path=='/api/journal') or (method=='POST' and path=='/api/journal/page'):
        before=data.get('before',2**63-1)
        if type(before) is not int or before<1 or before>2**63-1:
            raise ValueError('请重新打开手记列表')
        rows=db.execute(f'SELECT seq,{FIELDS} FROM journal_entries WHERE owner=? AND seq<? ORDER BY seq DESC LIMIT ?', (owner,before,PAGE_SIZE+1)).fetchall()
        return {'entries':[summary(row) for row in rows[:PAGE_SIZE]],'next':rows[PAGE_SIZE-1]['seq'] if len(rows)>PAGE_SIZE else None}
    if method=='GET' and path.startswith('/api/journal/image/'):
        row=owned(db,owner,path.rsplit('/',1)[-1],'image_b64,width,height')
        if not row['width']:
            raise ValueError('这篇手记没有照片')
        return {'mime':'image/jpeg','image':row['image_b64']}
    if method!='POST':
        return NotImplemented
    if path=='/api/journal/save':
        return save(db,owner,data)
    if path=='/api/journal/card':
        if not db.in_transaction:
            db.execute('BEGIN IMMEDIATE')
        row=owned(db,owner,data.get('id'),'seq,state')
        if row['state']!='published':
            raise ValueError('请先把草稿保存成手记')
        # Use the same per-source uniqueness as action and snapshot cards.
        note=clean(data.get('note',''),160,'卡片上的一句话')
        db.execute("""INSERT OR IGNORE INTO student_cards(user_id,source,source_id,title,kind,note,at)
                      VALUES(?, 'journal', ?, '此刻留影', 'settle', ?, ?)""",
                   (owner,row['seq'],note,int(datetime.now(timezone.utc).timestamp())))
        return {'ok':True}
    if path=='/api/journal/delete':
        if db.execute('DELETE FROM journal_entries WHERE owner=? AND id=? AND revision=?',(owner,entry_id(data.get('id')),checked_revision(data))).rowcount!=1:
            raise ValueError('手记已更改或已删除，请刷新后重试')
        return {'ok':True}
    if path not in ('/api/journal/reflect','/api/journal/look'):
        return NotImplemented
    if data.get('consent') is not True:
        raise ValueError('请先确认本次使用 AI 的内容')
    row=owned(db,owner,data.get('id'),FIELDS+',image_b64')
    if checked_revision(data)!=row['revision']:
        raise ValueError('手记已被修改，请刷新后重试')
    if path.endswith('/look'):
        if not row['width']:
            raise ValueError('请先保存一张照片')
        from companion_ai import look
        result=look(base64.b64decode(row['image_b64']),row['caption'])
        field='scene'
    else:
        if not (row['story'] or json.loads(row['words']) or row['need'] or row['context']):
            raise ValueError('请先写一点感受或选一个感受词')
        from companion_ai import reflect
        text='\n'.join(part for part in (row['story'],f"当时的场景：{row['context']}" if row['context'] else '') if part)
        result=reflect(text,json.loads(row['words']),row['need'])
        field='reflection'
    if not result or not isinstance(result.get('text'),str) or not result['text'].strip():
        return {'available':False,'message':'这次未获得模型回应，手记已保存。可以稍后再试。'}
    changed=db.execute(f'UPDATE journal_entries SET {field}=?,{field}_source=?,revision=revision+1 WHERE owner=? AND id=? AND revision=?',
                       (result['text'].strip()[:2800],str(result.get('source','模型'))[:100],owner,row['id'],row['revision'])).rowcount
    if not changed:
        raise ValueError('手记在生成时发生更改，请基于最新内容再试一次')
    return {'available':True,'entry':summary(owned(db,owner,row['id']))}
