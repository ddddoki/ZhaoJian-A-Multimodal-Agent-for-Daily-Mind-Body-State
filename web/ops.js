const actionNames={edit:'编辑草稿',draft:'新建草稿',publish:'发布'};
const stamp=value=>new Date(value).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
const style=`<style>.ops-space{display:grid;gap:16px}.ops-space .card{display:grid;gap:12px;margin:0}.ops-space .intro{background:#e6efe1}.ops-space p,.ops-space h1,.ops-space h2,.ops-space h3{margin:0}.ops-space .ops-row{display:flex;gap:9px;align-items:center;flex-wrap:wrap}.ops-space h1{font-size:clamp(1.8rem,4vw,2.6rem)}.ops-space .ops-copy{white-space:pre-wrap;overflow-wrap:anywhere}.ops-space .record{border-top:1px solid #d4e1d5;padding-top:12px;display:grid;gap:6px}.ops-space label{display:grid;gap:5px}.ops-space [hidden]{display:none!important}.ops-space .ops-tag{padding:3px 8px;border-radius:12px;background:#e6ede1;font-size:12px}</style>`;
export async function renderOps(root,ctx){
  const {api,escape:esc}=ctx,state=await api('/api/ops');
  const versions=state.versions,defaults=state.defaults,active=state.active;
  const previewRow=id=>versions.find(v=>v.id===id);
  function desc(key){return active[key]?previewRow(active[key]).description:defaults[key].description;}
  const drafts=versions.filter(v=>v.state==='draft'),logs=state.audit;
  root.innerHTML=style+`<section class="ops-space"><header class="card intro"><h1>行动库运营</h1><p>${esc(state.cohort)} · 编辑和发布学生端的小行动说明。</p></header><p class="error" role="alert" data-error></p><section class="card"><h2>当前行动</h2>${Object.entries(defaults).map(([k,v])=>`<article class="record"><div class="ops-row"><strong>${esc(v.title)}</strong><span class="ops-tag">${active[k]?'版本 '+active[k]:'内置版本'}</span></div><p class="ops-copy">${esc(desc(k))}</p><div class="ops-row"><button data-new="${esc(k)}">新建修改草稿</button>${active[k]?`<button data-history="${esc(k)}">选择回滚版本</button>`:''}</div></article>`).join('')}</section><section class="card" data-editor hidden></section><section class="card"><h2>待发布草稿</h2>${drafts.map(v=>`<article class="record"><div class="ops-row"><strong>${esc(defaults[v.kind].title)}</strong><span class="ops-tag">草稿 ${v.id}</span></div><p class="ops-copy">${esc(v.description)}</p><div class="ops-row">${v.creator===ctx.user.id?`<button data-edit="${v.id}">编辑草稿</button>`:''}${v.base_id===active[v.kind]?`<button data-review="${v.id}">预览发布</button>`:'<small>基于旧版本，请从当前行动新建修改。</small>'}</div></article>`).join('')||'<p>当前没有待发布草稿。</p>'}</section><section class="card" data-confirm hidden></section><section class="card"><h2>操作记录</h2>${logs.map(l=>`<div class="record"><strong>${l.event.startsWith('rollback:')?'回滚到 '+(l.event==='rollback:0'?'内置版本':'版本 '+esc(l.event.slice(9))):esc(actionNames[l.event])} · 版本 ${l.version_id}</strong><small>${esc(l.actor_name||'已移除的运营账号')} · ${stamp(l.at)}</small></div>`).join('')||'<p>编辑、发布和回滚后会留下记录。</p>'}</section></section>`;
  const q=sel=>root.querySelector(sel),editor=q('[data-editor]'),confirm=q('[data-confirm]'),error=q('[data-error]');
  const show=(el,html)=>{editor.hidden=true;confirm.hidden=true;el.hidden=false;el.innerHTML=html;el.scrollIntoView({block:'center'});};
  function perform(button,fn){return async()=>{error.textContent='';button.disabled=true;try{await fn();await ctx.refresh();}catch(e){error.textContent=e.message;error.scrollIntoView();}finally{button.disabled=false;}};}
  function edit(kind,version){
    show(editor,`<h2>${version?'编辑草稿':'新建草稿'} · ${esc(defaults[kind].title)}</h2><form><label>学生看到的行动说明<textarea name="description" maxlength="200" rows="4" required>${esc(version?version.description:desc(kind))}</textarea></label><div class="ops-row"><button class="primary">保存草稿</button><button type="button" data-cancel>取消</button></div></form>`);
    const form=editor.querySelector('form'),save=form.querySelector('button');form.onsubmit=e=>{e.preventDefault();perform(save,()=>api('/api/ops/draft',{kind,description:form.elements.description.value,...(version?{id:version.id}:{})}))();};
    editor.querySelector('[data-cancel]').onclick=()=>editor.hidden=true;
  }
  function review(v){
    show(confirm,`<h2>发布前确认</h2><strong>${esc(defaults[v.kind].title)} · ${esc(state.cohort)}</strong><small>当前说明</small><p class="ops-copy">${esc(desc(v.kind))}</p><small>发布后的说明</small><p class="ops-copy">${esc(v.description)}</p><div class="ops-row"><button data-publish class="primary">确认发布</button><button data-cancel>返回</button></div>`);
    const publish=confirm.querySelector('[data-publish]');publish.onclick=perform(publish,()=>api('/api/ops/publish',{id:v.id,reviewed:v.description}));confirm.querySelector('[data-cancel]').onclick=()=>confirm.hidden=true;
  }
  function history(kind){
    const past=[{id:0,description:defaults[kind].description},...versions.filter(v=>v.kind===kind&&v.state==='published'&&v.id!==active[kind])];
    show(confirm,`<h2>回滚 · ${esc(defaults[kind].title)}</h2><label>目标版本<select>${past.map(p=>`<option value="${p.id}">${p.id?'版本 '+p.id:'内置版本'}</option>`).join('')}</select></label><p>确认后将发布一个新版本，保留原有修改记录。</p><p class="ops-copy" data-target></p><div class="ops-row"><button class="primary" data-rollback>确认回滚</button><button data-cancel>返回</button></div>`);
    const select=confirm.querySelector('select'),refresh=()=>confirm.querySelector('[data-target]').textContent=past.find(v=>v.id===Number(select.value)).description;select.onchange=refresh;refresh();const go=confirm.querySelector('[data-rollback]');go.onclick=perform(go,()=>api('/api/ops/rollback',{kind,target:Number(select.value),current:active[kind]}));confirm.querySelector('[data-cancel]').onclick=()=>confirm.hidden=true;
  }
  for(const b of root.querySelectorAll('[data-new]'))b.onclick=()=>edit(b.dataset.new);
  for(const b of root.querySelectorAll('[data-edit]'))b.onclick=()=>{const v=previewRow(Number(b.dataset.edit));edit(v.kind,v);};
  for(const b of root.querySelectorAll('[data-review]'))b.onclick=()=>review(previewRow(Number(b.dataset.review)));
  for(const b of root.querySelectorAll('[data-history]'))b.onclick=()=>history(b.dataset.history);
}
