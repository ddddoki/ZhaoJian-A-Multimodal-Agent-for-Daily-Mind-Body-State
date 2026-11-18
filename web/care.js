const fmt=sec=>new Date(sec*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit',hour12:false});
const rules='<details><summary>曲线怎样得到？</summary><p class="care-help">按北京时间逐日计算。如果你做了快速自评，优先使用当天最后一次的心情：1、2、3、4、5 对应 −1、−0.5、0、+0.5、+1。如果当天没有快速自评，才使用已发布手记中本人选定的固定词。松了一口气、期待、开心、被理解、好奇记为 +1，平静为 0，有点乱、疲惫、委屈、焦虑为 −1。每篇先取已识别词的均值，再按北京时间对当天各篇取均值。「想念」「说不清」和自定义词不计分，缺记录的日期留空。最近两个连续自然日的数据点均不高于 −0.5，且最后一天为今天或昨天时，提示老师人工问候。曲线描述本人的自报变化，仅作为人工问候线索。</p></details>';

function layout(root,title,body){
  root.innerHTML='<div class="care-space"><header class="care-hero"><h1></h1><p></p></header><p class="care-msg" role="status"></p><div class="care-content care-space"></div></div>';
  root.querySelector('h1').textContent=title;
  root.querySelector('header p').textContent=body;
  return {content:root.querySelector('.care-content'),message:root.querySelector('.care-msg')};
}
function chart(curve){
  const points=curve.points;const x=i=>48+i*45,y=v=>50-32*v;
  const titles=['偏轻松','居中','偏吃力'];
  const axis=[1,0,-1].map((v,i)=>`<text x="0" y="${y(v)+3}" font-size="9" fill="#406657">${titles[i]}</text><path d="M39 ${y(v)}H329" stroke="#abc5b9" stroke-width=".6"/>`).join('');
  const nodes=points.map((p,i)=>{
    const day=p.date.slice(5).replace('-','/'), prev=points[i-1];
    const value=p.value===null?'无记录':p.value.toFixed(2);const has=p.value!==null;
    const line=has&&prev&&prev.value!==null?`<path d="M${x(i-1)} ${y(prev.value)}L${x(i)} ${y(p.value)}" fill="none" stroke="#358470" stroke-width="2.5"/>`:'';
    return `${line}${has?`<circle cx="${x(i)}" cy="${y(p.value)}" r="4" fill="#26715e"><title>${day} · ${value}</title></circle>`:''}<text x="${x(i)}" y="110" text-anchor="middle" font-size="9" fill="#4d6961">${day}</text>`;
  }).join('');
  let detail=points.map(p=>p.date.slice(5)+' '+(p.value===null?'无记录':p.value.toFixed(2))).join('，');
  return `<figure class="care-chart-wrap"><svg class="care-chart" viewBox="0 0 341 118" role="img" aria-label="近七日心情趋势：${detail}">${axis}${nodes}</svg><figcaption>近 7 天 · ${points.filter(p=>p.value!==null).length} 天有可用记录；缺口表示当天没有可用记录。</figcaption></figure>`;
}
function invoke(view,button,fn){return async e=>{e?.preventDefault();if(button.disabled)return;button.disabled=true;view.message.textContent='';try{await fn();}catch(err){view.message.textContent=err.message;}finally{button.disabled=false;}};}

export async function renderCareStudent(root,ctx){
  const {api,escape:esc}=ctx;const view=layout(root,'我的班级与授权','入班、授权和撤回都由你决定。');
  const state=await api('/api/care/student');if(!root.isConnected)return;
  const current=state.cohort||'尚未加入班级';
  view.content.innerHTML=`<section class="care-panel"><h2>我的班级</h2><strong>${esc(current)}</strong><div class="care-list">${state.invitations.map(i=>`<div class="care-row"><span><b>${esc(i.teacher)}</b> 邀请你加入 ${esc(i.cohort)}<small>有效至 ${fmt(i.expires)}。转班会终止旧班级的趋势授权和个别求助共享。</small></span><span><button data-answer="accept" data-key="${esc(i.id)}">同意加入</button><button data-answer="decline" data-key="${esc(i.id)}">拒绝</button></span></div>`).join('')||'<small>目前没有待处理的班级邀请。</small>'}</div></section><div class="care-cols"><section class="care-panel"><h2>老师会看到什么</h2><p>授权后，指定老师可查看滚动最近 7 天的曲线（含授权前的快速心情自评和已发布手记形成的点）和人工关怀提示。老师看不到手记原文、具体感受词、照片、经期或桌宠对话。</p>${chart(state.preview)}${rules}<p class="care-help">${state.preview.flag_day?'当前预览会触发一次「建议问候」提醒。':'当前没有触发人工问候提示。'}</p></section><section class="care-panel"><h2>按老师授权</h2>${state.teachers.map(t=>`<div class="care-row"><div><strong>${esc(t.name)}</strong><small>${t.until?'已授权至 '+fmt(t.until):'尚未授权'}</small></div>${t.until?`<button data-revoke="${t.id}">撤回</button>`:`<button data-open="${t.id}">设置授权</button>`}</div>`).join('')||'<p>当前班级还没有负责人，收到邀请后可在此设置。</p>'}<div data-consent></div><details><summary>最近的曲线访问</summary>${state.visits.map(v=>`<p>${esc(v.name)} · ${fmt(v.at)}</p>`).join('')||'<p>尚无查看记录。</p>'}</details></section></div>`;
  for(const b of view.content.querySelectorAll('[data-answer]'))b.onclick=invoke(view,b,async()=>{await api('/api/care/decision',{id:b.dataset.key,decision:b.dataset.answer});if(b.dataset.answer==='accept')await ctx.reloadUser();else await ctx.refresh();});
  for(const b of view.content.querySelectorAll('[data-revoke]'))b.onclick=invoke(view,b,async()=>{await api('/api/care/revoke',{teacher:Number(b.dataset.revoke)});await ctx.refresh();});
  const box=view.content.querySelector('[data-consent]');
  for(const b of view.content.querySelectorAll('[data-open]'))b.onclick=()=>{const id=Number(b.dataset.open),t=state.teachers.find(x=>x.id===id);
    box.innerHTML=`<form class="care-details"><strong>授权给 ${esc(t.name)}</strong><label>有效期<select><option value="3">3 天</option><option value="7">7 天</option><option value="14">14 天</option></select></label><label><input type="checkbox" required> 我已查看预览，同意这位老师在有效期内查看近 7 天曲线和提醒。</label><div><button class="primary" type="submit">确认授权</button> <button type="button">取消</button></div></form>`;
    const form=box.querySelector('form'),submit=form.querySelector('[type=submit]');form.querySelector('[type=button]').onclick=()=>box.replaceChildren();form.onsubmit=invoke(view,submit,async()=>{await api('/api/care/allow',{teacher:id,days:Number(form.querySelector('select').value),confirmed:form.querySelector('input').checked});await ctx.refresh();});
  };
}

export async function renderCareManager(root,ctx){
  const {api,escape:esc}=ctx;const view=layout(root,'班级关怀','邀请学生加入班级，查看学生主动授权的心情趋势。');
  view.content.innerHTML='<section class="care-panel"><h2>邀请学生入班</h2><form class="care-actions"><label>查找方式<select name="field"><option value="username">学生账号</option><option value="name">学生姓名</option></select></label><label>完整账号或姓名<input name="query" maxlength="60" required></label><button class="primary">发送邀请</button></form><div data-pending></div></section><section class="care-panel"><h2 data-heading>班级成员</h2><div data-roster class="care-list"></div></section>';
  const roster=view.content.querySelector('[data-roster]'),pending=view.content.querySelector('[data-pending]'),form=view.content.querySelector('form');
  let state=null,opened=null,detail=null,busy=false,revision=0;
  function paint(){
    view.content.querySelector('[data-heading]').textContent=state.cohort+' · 班级成员';
    pending.innerHTML=state.pending.length?`<small>待接受：${state.pending.map(p=>esc(p.name)+'（'+esc(p.username)+'）').join('、')}</small>`:'';
    roster.innerHTML=state.roster.map(m=>`<article><div class="care-row"><div><strong>${esc(m.name)}</strong><small>${esc(m.username)} · ${m.until?'授权至 '+fmt(m.until):'尚未授权趋势'}</small></div>${m.until?`<button data-id="${m.id}">${opened===m.id?'收起曲线':'查看曲线'}</button>`:''}</div>${m.flag_day?`<p class="care-warn">${m.followed?'已标记跟进':'建议人工问候'} · ${esc(m.flag_day)}，连续两天的自报趋势偏吃力。</p>`:''}${opened===m.id&&m.until&&detail?`<div class="care-details">${chart(detail)}${rules}${detail.flag_day&&!detail.followed?`<button data-follow="${m.id}">标记已跟进</button>`:''}</div>`:''}</article>`).join('')||'<p>暂无班级成员，可先用账号或姓名发邀请。</p>';
    for(const b of roster.querySelectorAll('[data-id]'))b.onclick=invoke(view,b,async()=>{const id=Number(b.dataset.id);const request=++revision;if(opened===id){opened=null;detail=null;paint();return;}opened=id;detail=null;paint();const target=await api('/api/care/curve',{student:id});if(request===revision&&opened===id&&root.isConnected){detail=target;paint();}});
    for(const b of roster.querySelectorAll('[data-follow]'))b.onclick=invoke(view,b,async()=>{await api('/api/care/follow',{student:Number(b.dataset.follow),day:detail.flag_day});opened=null;detail=null;await refresh();});
  }
  async function refresh(){
    if(busy||!root.isConnected)return;busy=true;
    try{
      const latest=await api('/api/care/manager');if(!root.isConnected)return;
      state=latest;
      const id=opened,request=revision,item=latest.roster.find(r=>r.id===id);
      if(id!==null&&(!item?.until||item.until*1000<=Date.now())){
        revision++;opened=null;detail=null;
      }else if(id!==null&&detail?.view){
        try{
          const updated=await api('/api/care/update',{student:id,view:detail.view});
          if(revision===request&&opened===id)detail=updated;
        }catch{
          if(revision===request&&opened===id){revision++;opened=null;detail=null;}
        }
      }
      if(root.isConnected&&document.visibilityState==='visible')paint();
    }catch(e){opened=null;detail=null;roster.replaceChildren();pending.replaceChildren();view.message.textContent=e.message;}finally{busy=false;}
  }
  form.onsubmit=invoke(view,form.querySelector('button'),async()=>{await api('/api/care/invite',Object.fromEntries(new FormData(form)));form.reset();view.message.textContent='邀请已发送，等待学生接受。';await refresh();});
  await refresh();
  if(!root.isConnected)return;
  const timer=setInterval(()=>{if(document.visibilityState==='visible')refresh();},5000);
  function visibility(){if(document.hidden){revision++;opened=null;detail=null;roster.replaceChildren();pending.replaceChildren();}else refresh();}
  document.addEventListener('visibilitychange',visibility);
  const observer=new MutationObserver(()=>{if(!root.isConnected){clearInterval(timer);document.removeEventListener('visibilitychange',visibility);observer.disconnect();}});
  observer.observe(document.querySelector('#app'),{childList:true,subtree:true});
}
