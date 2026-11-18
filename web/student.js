const css = `
.student-home-hero{min-height:clamp(260px,29vw,390px);display:flex;align-items:center;margin:0 0 20px;padding:clamp(22px,4vw,50px);border-radius:26px;border:1px solid #ffffffdf;isolation:isolate;overflow:hidden;position:relative;background:#d9ede0 url('/media/lightscape.webp') center 52% / cover no-repeat;box-shadow:0 15px 38px #5276741c}.student-home-hero:before{content:'';position:absolute;inset:0;z-index:-1;background:linear-gradient(96deg,#ecf9ecf5 4%,#f2f8eab8 35%,#dae9dc05 75%)}.student-home-hero>div{max-width:min(85%,445px)}.student-home-hero h1{font-family:'STIX Two Text','Songti SC',SimSun,serif;font-size:clamp(2.1rem,4.7vw,4.6rem);line-height:1.12;color:#163e38;margin:0 0 13px;font-weight:600;letter-spacing:-.045em}.student-home-hero .eyebrow{font-size:.78rem;letter-spacing:.12em;color:#40665a;margin-bottom:10px}.student-home-hero p{color:#334f46}.zj-journal-link{display:inline-flex;align-items:center;justify-content:space-between;gap:22px;border-radius:99px;background:#205447;color:#fff!important;padding:8px 16px;text-decoration:none;font-weight:650;font-size:.92rem}.zj-journal-link:hover{background:#306b5b}.zj-entry-preview span{display:inline-block;background:#e7efda;border:1px solid #d4e0cd;color:#385547;border-radius:16px;margin:0 4px 3px 0;padding:2px 9px;font-size:.8rem}.zj-entry-preview blockquote{border-left:2px solid #a2c3ad;padding:3px 12px;margin:9px 0 15px;white-space:pre-wrap}.zj-quick{margin-top:14px;padding-top:10px;border-top:1px solid #d9e2db}.zj-quick>summary{font-size:.87rem;color:#4b675d}.zj-quick>small{display:block;margin:.6rem 0}

.student-module {position:relative; padding-bottom:80px}
.shell .student-tabs {display:flex; flex-wrap:wrap; gap:6px; margin:0 0 20px}
.student-tabs button {border-color:transparent; background:transparent}
.student-tabs .selected {color:#164738; background:#d9e9d1; border-color:#bfceb7}
.student-module .card {margin-bottom:16px;overflow-wrap:anywhere}
.student-hero {position:relative; overflow:hidden; background:linear-gradient(120deg,#dcebd8,#f5efd2); min-height:200px; display:flex; align-items:center}
.student-hero>div:first-child {position:relative;z-index:1;max-width:75%}
.student-hero .mascot {right:9%;bottom:17%;transform:rotate(-6deg) scale(.85);transform-origin:bottom right}
.student-hero h1 {font-family:'STIX Two Text',SimSun,serif;font-weight:650;font-size:clamp(1.75rem,3.3vw,3rem)}
.student-module .eyebrow {font-size:.83rem;color:#466b50;letter-spacing:.06em}
.student-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,255px),1fr));gap:16px}
.scores {display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin:16px 0}
.scores>div {padding:10px 6px;border-radius:12px;text-align:center;background:#edf4e7}
.scores>div:nth-child(2){background:#f7eccf}.scores>div:nth-child(3){background:#e4eef1}.scores>div:nth-child(4){background:#f4e2de}
.scores strong,.student-row small {display:block}.scores strong {font-size:1.45rem}.scores strong small{font-size:.65rem}
.student-row{display:flex;gap:10px;align-items:center;justify-content:space-between;padding:9px 0;border-bottom:1px solid #dde4d9}.student-row:last-child{border:0}.student-row h2{margin:0}.student-row button{flex-shrink:0}
.growth{background:linear-gradient(140deg,#f5e9c9,#fffdf4)}
.student-overlay {position:fixed;inset:0;z-index:8;background:#1e342d66;display:grid;place-items:center;padding:15px}
.student-dialog {width:min(100%,460px);max-height:90dvh;overflow-y:auto;box-shadow:0 14px 60px #213b3226}.student-dialog .student-row{margin-bottom:12px}.student-dialog label small{float:right}
@media(max-width:620px){.student-hero .mascot{right:3%;bottom:9%;transform:rotate(-6deg) scale(.51)}.student-hero>div:first-child{max-width:82%}.student-tabs button{padding:.4rem .65rem}.student-grid{gap:0}.student-module .pet-window{max-height:73dvh}.scores>div{padding:6px 3px}}
`;
const dateText = (unix) => new Date(unix * 1000).toLocaleString('zh-CN', { month:'numeric', day:'numeric', hour:'2-digit', minute:'2-digit' });
const labels = {energy:'能量', tension:'紧绷', recovery:'恢复', mood:'心情'};
const anchors = {energy:['没什么力气','精力充沛'], tension:['很放松','很紧绷'], recovery:['还没缓过来','恢复得很好'], mood:['很低落','很愉快']};
const sections = ['今日','行动','成长卡','周回顾','个人线索'];

export async function renderStudent(root,ctx) {
  if(!document.getElementById('student-style')){const style=document.createElement('style');style.id='student-style';style.textContent=css;document.head.append(style);}
  const {api,escape:esc}=ctx;
  const req=(path,data)=>api('/api/student/'+path,data);
  let [state,campus,journal,dayPlan,classCare]=await Promise.all([
    req('overview'), api('/api/campus'), api('/api/journal'), api('/api/plan'), api('/api/care/student')
  ]);
  let offset=Date.now()/1000-state.now; let section='今日', dialog='', editing=null, clock;
  let actionKey=state.recommended, cardSource=null, status='';
  const button=(label,cmd,cls='',attrs='')=>`<button type="button" class="${cls}" data-cmd="${cmd}" ${attrs}>${label}</button>`;
  const active=()=>state.actions.find(s=>s.status==='active');
  const cardFor=(type,id)=>state.cards.some(c=>c.source===type&&c.source_id===id);
  const block=(title,content)=>`<section class="card"><h2>${title}</h2>${content}</section>`;
  const empty=(msg)=>`<p class="muted">${msg}</p>`;
  const tag=(s)=>`<small>${esc(s)}</small>`;
  function nextAction(){
    const a=active();const kind=a?a.kind:actionKey;const c=state.catalog[kind];
    return block(a?'进行中的小行动':'给现在的一件小事',`<p class="eyebrow">${a?'计时中':'约 '+c.seconds/60+' 分钟'}</p><h3>${esc(c.title)}</h3><p>${esc(c.description)}</p>${a?`<p><strong data-clock></strong></p>${button('结束并反馈','feedback','primary')} ${button('退出行动','cancel')}`:button('开始这个行动 →','start','primary',`data-kind="${kind}"`)}`);
  }
  function evidence(){
    if(!state.evidence.length) return '<small>暂无近期设备读数。你仍可独立完成自评。</small>';
    const lines=state.evidence.map(r=>{
      const compare=r.baseline==null
        ? `近 14 天有 ${r.days} 个可比日，满 3 天后显示中位数。`
        : `近 14 天共 ${r.days} 个可比日，同来源中位数 ${r.baseline} ${esc(r.unit)}。`;
      return `<li><strong>${esc(r.label)} ${r.value} ${esc(r.unit)}</strong><br><small>${dateText(r.at)} · ${esc(r.source)}</small><br>${compare}</li>`;
    }).join('');
    return `<details><summary>近期身体线索 · ${state.evidence.length} 项</summary><ul>${lines}</ul><p>身体线索另按采集时间展示。不同时间、活动和佩戴条件会影响读数；各维得分始终以你的自评为准。</p></details>`;
  }
  function dayAtGlance(){
    const stored=dayPlan.items.filter(item=>item.status==='planned');
    const picks=(dayPlan.items.length?stored:dayPlan.suggested).slice(0,3);
    const rows=picks.map(item=>`<li><time>${esc(item.time)}</time><div><strong>${esc(item.title)}</strong><small>${item.duration} 分钟${item.conflict?' · 与事务冲突':''}</small></div></li>`).join('');
    const noItems=dayPlan.items.length?'今天已没有待办的规划项。':'今天的可用时段已排满或已结束。';
    return `<section class="card glance"><header><h2>${dayPlan.items.length?'今天的规划':'今天可以这样安排'}</h2><a href="#plan">打开规划 ↗</a></header>
      ${rows?`<ol>${rows}</ol>`:`<p>${noItems}</p>`}
      <small>${dayPlan.items.length?'已保存的安排':picks.length?'建议时段，确认后加入今天':'可以从手记里选择一分钟行动'}</small></section>`;
  }
  function today(){
    const snapshot=state.snapshots[0];
    const last=journal.entries.find(e=>e.state==='published') || journal.entries[0];
    const story=last?.story||last?.caption||'';
    const status=last?`<div class="zj-entry-preview">${last.words.map(w=>`<span>${esc(w)}</span>`).join('')}<blockquote>${story?esc(story.slice(0,110))+(story.length>110?'…':''):'留下一张照片，也是一种记录。'}</blockquote></div>`:empty('一张照片、几个词，或一段还没想清楚的话，都能成为第一篇手记。');
    const quick=`<details class="zj-quick"><summary>身体线索与快速自评</summary>${evidence()}${snapshot?`<div class="scores">${Object.entries(labels).map(([k,v])=>`<div><small>${v}</small><strong>${snapshot[k]}<small> / 5</small></strong></div>`).join('')}</div><p>${tag('上次自评 · '+dateText(snapshot.at))} ${esc(snapshot.note)}</p>${button('更正自评','correct','',`data-id="${snapshot.id}"`)} ${!cardFor('snapshot',snapshot.id)?button('自评打卡领卡','check','',`data-source="snapshot" data-id="${snapshot.id}"`):''}`:''} ${button('新增快速自评','snapshot')}</details>`;
    return `<section class="student-home-hero"><div><h1>收下今天的<br>一个瞬间。</h1><p>用镜头、文字和心情词，写一页属于自己的手记。</p><div class="hero-actions"><a class="zj-journal-link" href="#journal">照一照 · 写手记 <span aria-hidden="true">↗</span></a><a class="zj-plan-link" href="#plan">一日规划 <span aria-hidden="true">→</span></a></div></div></section>${classCare.invitations.length?`<a class="class-invite-link" href="#care">你有 ${classCare.invitations.length} 条班级邀请 <strong>查看邀请 →</strong></a>`:''}<div class="student-grid">${block(last?'最近的心情手记':'心情手记',`${status}<a href="#journal">打开我的手记 →</a>${quick}`)}${dayAtGlance()}</div>${active()?nextAction():''}${campus.hints.length?block('校园提醒',campus.hints.map(h=>`<p>${esc(h)}</p>`).join('')+'<a href="#campus">打开校园日程 →</a>'):''}`;
  }
  function actions(){
    return `<h1>小行动</h1>${nextAction()}${block('换一种开始方式', Object.entries(state.catalog).map(([k,c])=>`<div class="student-row"><div><strong>${esc(c.title)}</strong><small>${c.seconds/60} 分钟 · ${esc(c.description)}</small></div>${button('选择','choose','',`data-kind="${k}"`)}</div>`).join(''))}${block('行动记录',state.actions.filter(a=>a.status!=='active').map(a=>`<div class="student-row"><div><strong>${esc(state.catalog[a.kind].title)}</strong><small>${dateText(a.at)} · ${a.status==='done'?esc(a.feedback):'已退出'}</small></div>${a.status==='done'&&!cardFor('action',a.id)?button('打卡领卡','check','',`data-source="action" data-id="${a.id}"`):''}</div>`).join('')||empty('完成的小行动会留在这里。'))}`;
  }
  function cards(){return `<h1>我的成长卡</h1><p>保存试过的小事，下次可以从这里重新开始。</p><div class="student-grid">${state.cards.map(c=>`<article class="card growth"><p class="eyebrow">${dateText(c.at)} · 私人卡片</p><h2>${esc(c.title)}</h2><p>${esc(c.note)||'这次尝试，已经被好好收下。'}</p>${button('再试一次','replay','primary',`data-kind="${c.kind}"`)} ${button('改一句话','editcard','',`data-id="${c.id}"`)} ${button('删除','delcard','',`data-id="${c.id}"`)}</article>`).join('')||block('还没有成长卡',`<p>完成自评或小行动后，点“打卡领卡”就能留下第一张。</p><a href="#journal">去写手记 →</a>`)}</div>`;}
  function experiment(){const e=state.experiment;let controls='';if(e.status==='offered')controls=button('试一试','experiment','primary','data-change="accept"')+button('换一个','experiment','','data-change="swap"')+button('本周跳过','experiment','','data-change="skip"');if(e.status==='accepted')controls=`<form data-form="experiment"><label>试过之后，有哪部分让你投入？（可选）<input name="reflection" maxlength="160"></label><button class="primary">记下体验</button>${button('本周跳过','experiment','','data-change="skip"')}</form>`;if(e.status==='skipped')controls=empty('本周已跳过。');if(e.status==='done')controls=`<p>本周已体验。${esc(e.reflection)}</p>`;return block('本周兴趣实验',`<h3>${esc(e.title)}</h3><p>${esc(e.description)}</p>${controls}`);}
  function week(){const w=state.weekly;const events=[...journal.entries.filter(r=>r.state==='published').map(r=>({at:Date.parse(r.updated)/1000,title:'写下心情手记',description:r.story||r.caption||r.words.join(' · ')})),...state.snapshots.map(r=>({at:r.at,title:'记录了四维状态',description:`能量 ${r.energy} · 紧绷 ${r.tension} · 恢复 ${r.recovery} · 心情 ${r.mood}`})),...state.actions.map(r=>({at:r.ended||r.at,title:state.catalog[r.kind].title,description:r.status==='done'?r.feedback:r.status==='active'?'进行中':'已退出'})),...state.cards.map(r=>({at:r.at,title:'获得成长卡',description:r.title}))].sort((a,b)=>b.at-a.at);return `<h1>周回顾</h1>${block('这一周的足迹',`<p>${w.since} 起 · 快速自评 <strong>${w.days}</strong> 天，完成了 <strong>${w.actions}</strong> 次小行动。</p>${w.daily.map(v=>`<div class="student-row"><span>${v.day}</span><span>当日平均心情 ${v.mood} / 5</span></div>`).join('')||''}`)}${experiment()}${block('个人时间线',events.slice(0,25).map(e=>`<div class="student-row"><div><strong>${esc(e.title)}</strong><small>${esc(e.description)}</small></div>${tag(dateText(e.at))}</div>`).join('')||empty('第一次记录后在这里回看。'))}`;}
  function clues(){return `<h1>个人线索</h1>${block('我愿意让桌宠记住的事',`<p>只保存你主动写下的偏好。提问时可以选择是否引用。</p><form data-form="memory"><label>一条偏好<input name="note" required maxlength="180" placeholder="例如：复习时喜欢先安静一分钟"></label><button>保存偏好</button></form>${state.memories.map(m=>`<div class="student-row"><span>${esc(m.note)}</span><div>${button('修改','editmemory','',`data-id="${m.id}"`)} ${button('删除','delmemory','',`data-id="${m.id}"`)}</div></div>`).join('')}`)}${block('穿戴读数手动记录',`<p>可手填设备显示的数值。每条记录保留时间与来源。</p><form data-form="observation"><label>指标<select name="kind">${['睡眠（小时）','步数（步）','心率（次/分）','HRV（毫秒）'].map(k=>`<option>${k}</option>`).join('')}</select></label><label>读数<input name="value" type="number" step="any" required></label><button>保存读数</button></form>${state.observations.map(o=>`<div class="student-row"><div><strong>${esc(o.kind)} · ${o.value}</strong><small>${dateText(o.at)} · ${esc(o.source)}</small></div>${button('删除','delobs','',`data-id="${o.id}"`)}</div>`).join('')}`)} `;}
  function modal(){
    if(!dialog)return '';
    let title,body;
    if(dialog==='snapshot'){title=editing?'更正这次状态':'快速自评';body=`<p>按现在的真实感觉各选一个分数。</p><form data-form="snapshot">${Object.entries(labels).map(([k,v])=>`<label>${v} <small>${anchors[k][0]} → ${anchors[k][1]}</small><select name="${k}" required>${editing?'':'<option value="">请选择</option>'}${[1,2,3,4,5].map(n=>`<option value="${n}" ${editing?.[k]===n?'selected':''}>${n}</option>`).join('')}</select></label>`).join('')}<label>给自己留一句话（可选）<input name="note" maxlength="240" value="${esc(editing?.note||'')}"></label><button class="primary">保存状态</button></form>`;}
    if(dialog==='memory'){title='修改私人偏好';body=`<form data-form="memory-edit"><label>下次希望小照记住什么？<textarea name="note" maxlength="180" required>${esc(editing.note)}</textarea></label><button class="primary">保存修改</button></form>`;}
    if(dialog==='feedback'){title='刚才的小行动怎么样？';body=`<form data-form="finish"><label>行动后的感觉<select required name="feedback"><option value="">选择感受</option><option>有帮助</option><option>没变化</option><option>不适合我</option></select></label><button class="primary">保存反馈</button></form>`;}
    if(dialog==='card'){title=editing?'编辑成长卡':'收下一张成长卡';body=`<form data-form="card"><label>留下一句话（可选）<textarea name="note" maxlength="160" placeholder="下次还想记得什么？">${esc(editing?.note||'')}</textarea></label><button class="primary">保存到卡册</button></form>`;}
    return `<div class="student-overlay"><section class="card student-dialog" role="dialog" aria-modal="true" aria-label="${title}"><div class="student-row"><h2>${title}</h2>${button('关闭','close')}</div>${body}<p class="error" data-error role="alert"></p></section></div>`;
  }
  function paint(){clearInterval(clock);root.innerHTML=`<div class="student-module"><nav class="student-tabs" aria-label="学生功能">${sections.map(s=>button(s,'section',s===section?'selected':'',`data-section="${s}" ${s===section?'aria-current="page"':''}`)).join('')}</nav>${status?`<p role="status">${esc(status)}</p>`:''}<p class="error" data-page-error role="alert"></p>${({'今日':today,'行动':actions,'成长卡':cards,'周回顾':week,'个人线索':clues}[section])()}${modal()}</div>`;
    const el=root.querySelector('[data-clock]'), a=active(); if(el&&a){const diff=offset;const tick=()=>{if(!el.isConnected){clearInterval(clock);return;}const n=Math.max(0,Math.ceil(a.at+state.catalog[a.kind].seconds-Date.now()/1000+diff));el.textContent=n?`${Math.floor(n/60)}:${String(n%60).padStart(2,'0')}`:'计时结束，可以填写反馈了';};tick();clock=setInterval(tick,500);}
    if(dialog)root.querySelector('.student-dialog select,.student-dialog textarea')?.focus();
  }
  function error(e){const box=root.querySelector('.student-dialog [data-error]')||root.querySelector('[data-page-error]'); if(box){box.textContent=e.message;box.scrollIntoView({block:'nearest'});}}
  async function sync(msg=''){state=await req('overview');offset=Date.now()/1000-state.now;status=msg;paint();}
  root.onclick=async e=>{const b=e.target.closest('[data-cmd]');if(!b)return;const {cmd,id,kind,source}=b.dataset;status='';try{
    if(cmd==='section'){section=b.dataset.section;} else if(cmd==='snapshot'||cmd==='correct'){editing=id?state.snapshots.find(r=>r.id===Number(id)):null;dialog='snapshot';}
    else if(cmd==='close'){dialog='';editing=null;}else if(cmd==='choose'||cmd==='replay'){if(active()&&active().kind!==kind)throw new Error('请先完成或退出当前行动');actionKey=kind;section='行动';}
    else if(cmd==='start'){await req('start',{kind});return await sync('行动已开始。');}else if(cmd==='cancel'){if(!confirm('退出这次行动？'))return;await req('cancel',{id:active().id});return await sync('已退出本次行动。');}
    else if(cmd==='feedback'){dialog='feedback';}else if(cmd==='check'||cmd==='editcard'){editing=cmd==='editcard'?state.cards.find(c=>c.id===Number(id)):null;cardSource={source,source_id:Number(id)};dialog='card';}
    else if(cmd==='editmemory'){editing=state.memories.find(m=>m.id===Number(id));dialog='memory';}
    else if(['delcard','delmemory','delobs'].includes(cmd)){if(!confirm('确定删除这条私人记录？'))return;await req(({delcard:'card-delete',delmemory:'memory-delete',delobs:'observation-delete'})[cmd],{id:Number(id)});return await sync('记录已删除。');}
    else if(cmd==='experiment'){await req('experiment',{week:state.weekly.since,change:b.dataset.change});return await sync();}paint();
  }catch(err){error(err);}};
  root.onsubmit=async e=>{const form=e.target.closest('form[data-form]');if(!form)return;e.preventDefault();const d=Object.fromEntries(new FormData(form));const key=form.dataset.form;const submit=form.querySelector('button');submit.disabled=true;try{
    if(key==='snapshot'){for(const k of Object.keys(labels))d[k]=Number(d[k]);if(editing)d.id=editing.id;await req('snapshot',d);section='今日';}
    if(key==='finish'){await req('finish',{id:active().id,feedback:d.feedback});section='行动';}
    if(key==='card'){await req(editing?'card-edit':'card',editing?{id:editing.id,note:d.note}:{...cardSource,note:d.note});section='成长卡';}
    if(key==='experiment')await req('experiment',{week:state.weekly.since,change:'complete',reflection:d.reflection});
    if(key==='memory-edit')await req('memory-edit',{id:editing.id,note:d.note});
    if(key==='memory')await req('memory',d);
    if(key==='observation')await req('observation',{...d,value:Number(d.value)});
    dialog='';editing=null;await sync('已保存。');if(key==='snapshot'){actionKey=state.recommended;paint();}
  }catch(err){error(err);}finally{submit.disabled=false;}};
  root.onkeydown=e=>{if(e.key==='Escape'&&dialog){dialog='';paint();}};
  paint();
}
