import {mountAfterJournal} from './planner.js';
const words = ['松了一口气','期待','开心','被理解','平静','好奇','想念','有点乱','疲惫','委屈','焦虑','说不清'];
const prompts = ['今天有什么细节，让你停顿了一下？','如果把今天写成一幅画，你会画下什么？','此刻，你希望有人理解哪件小事？','今天什么时候，你感到自己被接住了？'];
const needs = ['有人听我说','理清思绪','歇一会儿','迈出第一步'];
const blank = () => ({words:[],story:'',context:'',need:'',caption:'',state:'draft'});
const timeLabel = stamp => new Date(stamp).toLocaleString('zh-CN',{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});

async function photoPixels(file) {
  if (!['image/jpeg','image/png','image/webp'].includes(file.type) || file.size > 16*1024*1024)
    throw new Error('请选择 16 MB 以内的 JPG、PNG 或 WebP 照片');
  const bitmap = await createImageBitmap(file);
  try {
    const scale=Math.min(1,1440/Math.max(bitmap.width,bitmap.height));
    const canvas=document.createElement('canvas');
    canvas.width=Math.max(1,Math.round(bitmap.width*scale));canvas.height=Math.max(1,Math.round(bitmap.height*scale));
    const context=canvas.getContext('2d',{alpha:false});
    context.fillStyle='white'; context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(bitmap,0,0,canvas.width,canvas.height);
    const image=canvas.toDataURL('image/jpeg',.87);if(!image.startsWith('data:image/jpeg;base64,'))throw new Error('无法读取图片，请换一张试试');
    return image;
  } finally {bitmap.close();}
}

export async function renderJournal(root,ctx){
  const esc=ctx.escape;
  const [page,ai]=await Promise.all([ctx.api('/api/journal'),ctx.api('/api/ai/status').catch(()=>({}))]);
  if(!root.isConnected)return;
  const entries=page.entries;let next=page.next, entry=blank(),selected=null, replacement, preview='',promptIndex=0, busy=false,dirty=false,pictureTicket=0;
  root.innerHTML='<div class="j-space"></div>';const view=root.firstElementChild;
  const $=s=>view.querySelector(s);
  const message=(text)=>{const target=$('[data-j-msg]');if(target)target.textContent=text;};
  const count=()=>{const c=$('[data-j-count]');if(c)c.textContent=entry.story.length+' / 4000';};
  function chip(w){return '<button type="button" data-word="'+esc(w)+'" aria-pressed="'+entry.words.includes(w)+'">'+esc(w)+'</button>';}
  function form(){
    return `<section class="j-panel j-compose" aria-label="写手记"><div class="j-section-head"><h2>${entry.id?'编辑这一页':'写下此刻'}</h2><button type="button" class="j-link" data-prompt>换个问题 ↻</button></div>
    <form data-jform><label class="j-story-label" for="j-story">${prompts[promptIndex]}</label><textarea id="j-story" class="j-story" name="story" maxlength="4000" placeholder="可以写一句话，也可以慢慢展开……">${esc(entry.story)}</textarea><div class="j-count" data-j-count></div>
    <fieldset><legend>此刻的感受 <small>可以同时有几种</small></legend><div class="j-chips" data-words>${[...new Set([...words,...entry.words])].map(chip).join('')}</div><div class="j-custom"><input data-custom maxlength="20" aria-label="自定义感受词" placeholder="用自己的词"><button type="button" data-addword>添加</button></div></fieldset>
    <div class="j-pair"><label>发生在哪里，和谁有关？<input name="context" maxlength="160" value="${esc(entry.context)}" placeholder="例如：晚自习回宿舍的路上"></label><label>我现在想要<input name="need" maxlength="160" list="j-needs" value="${esc(entry.need)}" placeholder="写下需要，或选一个"><datalist id="j-needs">${needs.map(n=>'<option value="'+n+'">').join('')}</datalist></label></div>
    <section class="j-photo"><div class="j-section-head"><div><h3>照一照</h3><p>放一张今天的照片，让它陪你记住这一刻。</p></div><span aria-hidden="true" class="j-camera">◉</span></div>
      <div class="j-preview" data-photo-preview></div><label class="j-pick">选择照片<input type="file" accept="image/jpeg,image/png,image/webp" data-file></label><button type="button" data-remove-photo class="j-link" ${entry.width||preview?'':'hidden'}>移除照片</button>
      <label class="j-caption" data-caption ${entry.width||preview?'':'hidden'}>照片里的故事<input name="caption" maxlength="240" value="${esc(entry.caption)}" placeholder="这张照片对你意味着什么？"></label>
      <small>保存时会上传去除位置等附加信息后的照片，仅你的账号可查看。</small></section>
    <div class="j-savebar"><button class="j-primary" type="submit">保存手记</button><button type="button" data-draft>存为草稿</button>${entry.id?'<button type="button" class="j-link" data-cancel>取消编辑</button>':''}</div></form></section>`;
  }
  function timeline(){
    return `<section class="j-panel j-timeline"><div class="j-section-head"><h2>我的时间线</h2><button type="button" data-new class="j-link">＋ 新手记</button></div>
    <div class="j-list">${entries.length?entries.map(e=>`<button type="button" class="j-entry" data-open="${esc(e.id)}" aria-pressed="${selected===e.id}"><span class="j-date">${timeLabel(e.created)}${e.state==='draft'?' · 草稿':''}</span><strong>${esc((e.story||e.caption||e.words.join('、')||e.need||e.context||'有照片的一天').slice(0,68))}</strong><span class="j-entry-tags">${e.width?'▣ 照片　':''}${esc(e.words.slice(0,3).join(' · '))}</span></button>`).join(''):'<p class="j-empty">写下的文字和上传的照片，会按时间收在这里。</p>'}</div>${next?'<button data-more type="button">查看更早的手记</button>':''}</section>`;
  }
  function detail(e){
    const showAnswer=(title,text,source)=>text?`<div class="j-answer"><h3>${title}</h3><p>${esc(text)}</p><small>${esc(source)}</small></div>`:'';
    const modelLabel=x=>x?.available?'可使用 '+(x.model||x.provider||'已连接模型'):'模型暂不可用';
    return `<article class="j-panel j-detail"><div class="j-section-head"><div><small>${timeLabel(e.created)}${e.state==='draft'?' · 草稿':''}</small><h2>这一天的手记</h2></div><button class="j-link" data-edit>${e.state==='draft'?'继续写':'编辑'}</button></div>
    <div class="j-detail-words">${e.words.map(w=>'<span>'+esc(w)+'</span>').join('')}</div>${e.story?'<p class="j-prose">'+esc(e.story)+'</p>':''}
    ${e.context?'<p><strong>当时的场景</strong>　'+esc(e.context)+'</p>':''}${e.need?'<p><strong>我现在想要</strong>　'+esc(e.need)+'</p>':''}
    ${e.width?'<figure><div data-detail-photo>正在读取照片…</div><figcaption>'+esc(e.caption)+'</figcaption></figure>':''}
    ${e.state==='published'?'<div data-next-step>正在整理接下来的行动…</div>':''}
    ${showAnswer('文字回声',e.reflection,e.reflection_source)}${showAnswer('照片场景线索',e.scene,e.scene_source)}
    <details class="j-ai"><summary>邀请小照读一读</summary><div><p>每次单独选择交给模型的内容。已保存的手记可以直接回看。</p>
    ${e.story||e.words.length||e.need||e.context?`<p><small>文字 · ${esc(modelLabel(ai?.text))}</small></p><button data-model="reflect">发送本篇文字，生成回声</button>`:''}
    ${e.width?`<p><small>视觉 · ${esc(modelLabel(ai?.vision))}</small></p><button data-model="look">分析这张照片的场景</button>`:''}</div></details>
    ${e.state==='published'?'<details class="j-ai"><summary>为此刻打卡，收一张成长卡</summary><p>「此刻留影」将保存在你的卡册中。你可以另外写一句，或留空。</p><label>想在卡上留下什么？<input data-card-note maxlength="160"></label><button type="button" data-card>领取成长卡</button></details>':''}
    <details class="j-del"><summary>删除手记</summary><p>文字、照片和已保存的 AI 回应将一并删除。</p><button type="button" data-delete>确认删除这一篇</button></details></article>`;
  }
  function remember(item){const i=entries.findIndex(e=>e.id===item.id);if(i<0)entries.unshift(item);else entries[i]=item;}
  function startEdit(item){entry=item?{...item,words:[...item.words]}:blank();selected=null;replacement=undefined;preview='';dirty=false;pictureTicket++;paint();}
  function allowLeave(){return !dirty||window.confirm('离开会舍弃尚未保存的修改。继续吗？');}
  async function run(op){if(busy)return;busy=true;view.setAttribute('aria-busy','true');const controls=[...view.querySelectorAll('button,input,textarea')].filter(x=>!x.disabled);controls.forEach(x=>x.disabled=true);try{message('');await op();}catch(e){message(e.message||'请稍后重试');}finally{busy=false;view.removeAttribute('aria-busy');controls.forEach(x=>x.disabled=false);}}
  async function requestPhoto(id,container){const ticket=pictureTicket;try{const photo=await ctx.api('/api/journal/image/'+id);if(!container?.isConnected||ticket!==pictureTicket)return;const img=document.createElement('img');img.alt='我上传的手记照片';img.src='data:image/jpeg;base64,'+photo.image;container.replaceChildren(img);}catch(e){if(container?.isConnected)container.textContent=e.message;}}
  async function submit(state){
    const payload={words:entry.words,story:entry.story,context:entry.context,need:entry.need,caption:entry.caption,state};
    if(entry.id){payload.id=entry.id;payload.revision=entry.revision;}
    if(replacement!==undefined)payload.image=replacement;
    const saved=await ctx.api('/api/journal/save',payload);remember(saved);selected=saved.id;dirty=false;replacement=undefined;preview='';paint();message(state==='draft'?'草稿已保存，可以稍后继续写。':'手记已保存。');
  }
  function paint(){
    const active=entries.find(e=>e.id===selected);
    view.innerHTML=`<header class="j-hero"><div><p class="j-date">${new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</p><h1>心情手记</h1><p>今天的你，有什么想留下？</p></div><div class="j-ripple" aria-hidden="true"><i></i><i></i><i></i></div></header>
    <p class="j-feedback" data-j-msg role="status" aria-live="polite"></p><div class="j-layout">${active?detail(active):form()}${timeline()}</div>`;
    $('[data-new]').onclick=()=>{if(allowLeave()) startEdit(null);};
    view.querySelectorAll('[data-open]').forEach(b=>b.onclick=()=>{if(allowLeave()){dirty=false;selected=b.dataset.open;paint();}});
    const more=$('[data-more]');if(more)more.onclick=()=>run(async()=>{const morePage=await ctx.api('/api/journal/page',{before:next});entries.push(...morePage.entries);next=morePage.next;paint();});
    if(active){
      if(active.state==='published')mountAfterJournal($('[data-next-step]'),ctx,active.id);
      if(active.width)requestPhoto(active.id,$('[data-detail-photo]'));
      $('[data-edit]').onclick=()=>startEdit(active);
      const card=$('[data-card]');if(card)card.onclick=()=>run(async()=>{await ctx.api('/api/journal/card',{id:active.id,note:$('[data-card-note]').value});message('「此刻留影」已在成长卡册，同一篇手记只发一张。');});
      $('[data-delete]').onclick=()=>run(async()=>{await ctx.api('/api/journal/delete',{id:active.id,revision:active.revision});entries.splice(entries.findIndex(e=>e.id===active.id),1);startEdit(null);message('手记已删除。');});
      view.querySelectorAll('[data-model]').forEach(b=>b.onclick=()=>run(async()=>{message('小照正在读这一页…');const result=await ctx.api('/api/journal/'+b.dataset.model,{id:active.id,revision:active.revision,consent:true});if(result.available){remember(result.entry);paint();message('已保存本次模型回应。');}else message(result.message);}));
      return;
    }
    const f=$('[data-jform]');count();
    for(const name of ['story','context','need','caption'])f.elements[name].oninput=e=>{entry[name]=e.target.value;dirty=true;count();};
    $('[data-prompt]').onclick=()=>{promptIndex=(promptIndex+1)%prompts.length;$('.j-story-label').textContent=prompts[promptIndex];};
    function toggle(word){const idx=entry.words.indexOf(word);if(idx>=0)entry.words.splice(idx,1);else if(entry.words.length<6)entry.words.push(word);else{message('这篇最多放六个感受词。');return;}dirty=true;renderWords();}
    function renderWords(){const row=$('[data-words]');row.innerHTML=[...new Set([...words,...entry.words])].map(chip).join('');row.querySelectorAll('[data-word]').forEach(b=>b.onclick=()=>toggle(b.dataset.word));}
    renderWords(); const custom=$('[data-custom]');$('[data-addword]').onclick=()=>{const w=custom.value.trim();if(w&&!entry.words.includes(w))toggle(w);custom.value='';};custom.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();$('[data-addword]').click();}};
    const remove=$('[data-remove-photo]'),slot=$('[data-photo-preview]'),file=$('[data-file]');const draw=()=>{slot.replaceChildren();remove.hidden=!preview; $('[data-caption]').hidden=!preview; if(preview){const image=new Image();image.src=preview;image.alt='即将保存的照片';slot.append(image);}};
    if(preview)draw();else if(entry.width&&replacement!==null)requestPhoto(entry.id,slot);
    remove.onclick=()=>{pictureTicket++;replacement=null;preview='';entry.caption='';f.elements.caption.value='';file.value='';dirty=true;draw();};
    file.onchange=async()=>{const picked=file.files[0];if(!picked)return;const ticket=++pictureTicket;try{f.querySelectorAll('.j-savebar button').forEach(b=>b.disabled=true);message('正在准备照片…');const uri=await photoPixels(picked);if(ticket!==pictureTicket||!slot.isConnected)return;preview=uri;replacement=uri.split(',')[1];dirty=true;draw();message('照片准备好了，保存手记后完成上传。');}catch(e){message(e.message);}finally{if(ticket===pictureTicket&&f.isConnected)f.querySelectorAll('.j-savebar button').forEach(b=>b.disabled=false);}};
    f.onsubmit=e=>{e.preventDefault();run(()=>submit('published'));};$('[data-draft]').onclick=()=>run(()=>submit('draft'));
    const cancel=$('[data-cancel]');if(cancel)cancel.onclick=()=>{if(allowLeave()){dirty=false;selected=entry.id;paint();}};
  }
  paint();
}
