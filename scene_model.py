"""On-device CLIP image/text matching for a small vocabulary of photographic scenes."""
from functools import lru_cache
from io import BytesIO
import json
from pathlib import Path

FOLDER = Path(__file__).parent / '.local' / 'ai' / 'clip'
# CLIP compares pixels with neutral scene descriptions. It does not assess the person.
SCENES = {
    '绿地或树木': 'a photograph of a garden with green trees',
    '湖泊或山景': 'a landscape photograph of a lake and mountains',
    '天空或云层': 'a photograph of the sky and clouds',
    '校园建筑': 'a photograph of school buildings outdoors',
    '书本或书桌': 'a photograph of books on a study desk',
    '室内空间': 'a photograph of the inside of a room',
    '食物或饮品': 'a photograph of food or a drink',
    '街道或道路': 'a photograph of a city street',
    '人物': 'a photograph of a person',
    '动物': 'a photograph of a pet animal',
    '屏幕或文字': 'a photograph of a screen displaying text',
}


def ready():
    import importlib.util
    return all((FOLDER / name).is_file() for name in ('vision.onnx','text.onnx','tokenizer.json')) and all(
        importlib.util.find_spec(name) for name in ('PIL','onnxruntime','numpy'))


@lru_cache(maxsize=1)
def load_model():
    import numpy as np
    import onnxruntime as ort
    vocab = json.loads((FOLDER / 'tokenizer.json').read_text(encoding='utf-8'))['model']
    ranks = {tuple(m.split() if isinstance(m,str) else m):i for i,m in enumerate(vocab['merges'])}
    def encode(sentence):
        ids = [vocab['vocab']['<|startoftext|>']]
        for word in sentence.split():
            symbols = [*word[:-1], word[-1]+'</w>']
            while len(symbols)>1:
                pairs=list(zip(symbols,symbols[1:]))
                best=min(pairs,key=lambda p:ranks.get(p,10**9))
                if best not in ranks:break
                merged=[]; i=0
                while i<len(symbols):
                    if tuple(symbols[i:i+2])==best:merged.append(''.join(best));i+=2
                    else:merged.append(symbols[i]);i+=1
                symbols=merged
            ids.extend(vocab['vocab'][s] for s in symbols)
        return ids+[vocab['vocab']['<|endoftext|>']]
    prompts=[encode(s) for s in SCENES.values()]
    width=max(map(len,prompts)); ids=np.array([p+[0]*(width-len(p)) for p in prompts],dtype='int64')
    mask=np.array([[1]*len(p)+[0]*(width-len(p)) for p in prompts],dtype='int64')
    opts=ort.SessionOptions(); opts.intra_op_num_threads=3
    encoder=ort.InferenceSession(str(FOLDER/'text.onnx'),opts,providers=['CPUExecutionProvider'])
    inputs={'input_ids':ids,'attention_mask':mask}
    vectors=encoder.run(['text_embeds'],{k.name:inputs[k.name] for k in encoder.get_inputs()})[0]
    vectors/=np.linalg.norm(vectors,axis=1,keepdims=True)
    vision=ort.InferenceSession(str(FOLDER/'vision.onnx'),opts,providers=['CPUExecutionProvider'])
    return vision,vectors


def describe(image_bytes):
    import numpy as np
    from PIL import Image,ImageOps
    vision,labels=load_model()
    with Image.open(BytesIO(image_bytes)) as opened:
        image=ImageOps.fit(ImageOps.exif_transpose(opened).convert('RGB'),(224,224),method=Image.Resampling.BICUBIC)
        pixels=np.asarray(image,dtype=np.float32)/255
    pixels=(pixels-np.array([.48145466,.4578275,.40821073],dtype='float32'))/np.array([.26862954,.26130258,.27577711],dtype='float32')
    emb=vision.run(['image_embeds'],{'pixel_values':pixels.transpose(2,0,1)[None,:,:,:]})[0][0]
    sims=labels@(emb/np.linalg.norm(emb));best=int(sims.argmax())
    ordered=np.sort(sims)
    if sims[best]<.20 or ordered[-1]-ordered[-2]<.006:
        return '照片中的场景不够明确。你拍下它时，最想记住的是哪处细节？'
    return f'在现有场景类别里，这张照片更接近「{list(SCENES)[best]}」。当时有什么细节让你想按下快门？'
