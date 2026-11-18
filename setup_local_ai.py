"""Install the pinned Windows CPU text runtime and CLIP models for this checkout."""
import argparse
from hashlib import sha256
from pathlib import Path
import platform
from urllib.request import Request,urlopen
from zipfile import ZipFile
from tempfile import TemporaryDirectory
import shutil

ROOT=Path(__file__).resolve().parent/'.local'/'ai'
VISION='https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/6b7c523703ae26e39be4b03774966f8571c7f523/'
FILES=[
    ('model.gguf','https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf','6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e'),
    ('clip/vision.onnx',VISION+'onnx/vision_model_quantized.onnx','583fd1110a514667812fee7d684952aaf82a99b959760c8d7dca7e0ab9839299'),
    ('clip/text.onnx',VISION+'onnx/text_model_quantized.onnx','73baab855d406190da9faa498cfedf65f15cf309f4cc7385b7b032e6d08e5c3a'),
    ('clip/tokenizer.json',VISION+'tokenizer.json','f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd'),
]
RUNTIME=('llama-b12521.zip','https://github.com/ggml-org/llama.cpp/releases/download/b12521/llama-b12521-bin-win-cpu-x64.zip','bd4e093bce292452248c318d4b176fbfebe1ca43a7f3779ebb3846fe7753653e')


def digest(file):
    h=sha256()
    with file.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def fetch(name,url,expected):
    path=ROOT/name;path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and digest(path)==expected:return path
    print('下载并校验',name,flush=True)
    with TemporaryDirectory(dir=path.parent) as tmp:
        temp=Path(tmp)/'download'
        with urlopen(Request(url,headers={'User-Agent':'Zhaojian-local-setup'}),timeout=90) as src,temp.open('wb') as dest:
            shutil.copyfileobj(src,dest,1024*1024)
        if digest(temp)!=expected:raise ValueError(f'{name} 文件校验失败，请重新运行')
        temp.replace(path)
    return path


def main():
    parser=argparse.ArgumentParser(description='下载照见的本机推理文件（全部约 1.3 GB）')
    parser.add_argument('--vision-only',action='store_true')
    args=parser.parse_args()
    if not args.vision_only and (platform.system()!='Windows' or platform.machine().upper() not in ('AMD64','X86_64')):
        parser.error('此文本运行包面向 Windows x64；可用 --vision-only 并自行配置本机 Ollama。')
    for file in FILES:
        if args.vision_only and file[0]=='model.gguf':continue
        fetch(*file)
    if not args.vision_only:
        archive=fetch(*RUNTIME)
        with ZipFile(archive) as z:z.extractall(ROOT/'runtime')
    print('模型文件就绪。启动照见后，可在手记和小照对话中选择使用本机模型。')


if __name__=='__main__':main()
