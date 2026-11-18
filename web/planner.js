const route='/api/plan';
const progressLabel={planned:'待进行',done:'已完成',skipped:'已跳过'};

function historyText(state){
  if(!state.samples)return '近两周还没有已发布手记，先从通用的轻量行动试起。';
  if(state.samples<3)return `近两周有 ${state.samples} 篇手记，可参考的记录还少；今天先试试适合你的一项。`;
  return `参考近两周最近 ${state.samples} 篇手记里的需要、感受词和你标为有帮助的行动。`;
}

function describeChoices(ctx,items){
  return items.map(i=>`<li><time>${ctx.escape(i.time)}</time><span>${ctx.escape(i.title)}</span><small>${i.duration} 分钟</small></li>`).join('');
}

export async function mountAfterJournal(node,ctx,entry){
  const load=()=>ctx.api(route+'/minute',{entry});
  try{
    let [action,plan]=await Promise.all([load(),ctx.api(route)]);
    if(!node.isConnected)return;
    const esc=ctx.escape;
    let clock;
    function draw(){
      if(clock)clearInterval(clock);
      const items=plan.items.length?plan.items.filter(i=>i.status==='planned'):plan.suggested;
      node.innerHTML=`<section class="zp-after"><div class="zp-minute"><small>此刻 · 1 分钟</small><h3>${esc(action.title)}</h3><p>${esc(action.description)}</p><p class="zp-note">${esc(action.reason)}</p>
        <div class="zp-buttons">${action.done?'<strong>这一分钟已完成 ✓</strong>':action.started?'<output data-timer></output><button type="button" data-minute="done">记录完成</button><button type="button" data-minute="stop" class="zp-quiet">结束计时</button>':'<button class="zp-primary" type="button" data-minute="start">开始 1 分钟</button>'}</div></div>
        <div class="zp-day"><small>接下来 · 今日规划</small><h3>${plan.items.length?'今天已保存的安排':'今天可以这样安排'}</h3><p class="zp-note">${esc(historyText(plan))}</p>
        ${items.length?`<ul class="zp-preview">${describeChoices(ctx,items)}</ul>`:`<p>${plan.items.length?'今天已经没有待进行的安排。':'今天的建议时段已结束或排满，先把剩下的时间留给自己。'}</p>`}
        <a href="#plan">查看与调整今日规划 <span aria-hidden="true">↗</span></a></div><p class="zp-alert" role="status"></p></section>`;
      if(!action.done && action.started){
        const adjusted=(Date.now()/1000)-action.now;
        const tick=()=>{
          if(!node.isConnected){clearInterval(clock);return;}
          const left=Math.max(0,60-Math.floor(Date.now()/1000-adjusted-action.started));
          node.querySelector('[data-timer]').textContent=left?`还剩 ${left} 秒`:'一分钟到了';
          node.querySelector('[data-minute="done"]').disabled=!!left;
          if(left===0)clearInterval(clock);
        };
        clock=setInterval(tick,250);tick();
      }
      for(const button of node.querySelectorAll('[data-minute]'))button.onclick=async()=>{
        button.disabled=true;
        try{action=await ctx.api(route+'/minute/'+button.dataset.minute,{entry});if(node.isConnected)draw();}
        catch(error){if(node.isConnected)node.querySelector('[role=status]').textContent=error.message;button.disabled=false;}
      };
    }
    draw();
  }catch(error){if(node.isConnected)node.textContent='暂时无法读取行动建议：'+error.message;}
}

export async function renderPlan(root,ctx){
  let state=await ctx.api(route);if(!root.isConnected)return;
  const esc=ctx.escape;let message='',editing=null,busy=false;
  async function update(path,data,notice){
    if(busy)return;busy=true;
    root.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{state=await ctx.api(route+'/'+path,data);message=notice;editing=null;}
    catch(error){message=error.message;}
    finally{busy=false;if(root.isConnected)draw();}
  }
  function card(item){
    const id=item.id, editable=item.status==='planned';
    return `<article class="zp-slot"><div class="zp-time"><time>${esc(item.time)}</time><span>${item.duration} 分钟</span></div><div class="zp-task">
    <div class="zp-heading"><h3>${esc(item.title)}</h3><small>${progressLabel[item.status]}</small></div><p>${esc(item.description)}</p>
    <p class="zp-note">${esc(item.reason)}</p>${item.conflict && editable?'<p class="zp-attn">课表已经变化，这项安排与校园事务重叠。</p>':''}${item.past&&editable?'<p class="zp-note">这个时段已过。可以补记完成、调整或跳过。</p>':''}
    ${editable?`<div class="zp-buttons"><button data-done="${id}" class="zp-primary">已完成</button><button data-change="${id}">换时段</button><button data-skip="${id}" class="zp-quiet">跳过</button></div>`:''}
    ${editing===id?`<form class="zp-move" data-form="${id}"><label>新的开始时间<input type="time" name="time" required value="${item.time}" min="07:30" max="22:29"></label><button>保存时间</button></form>`:''}</div></article>`;
  }
  function draw(){
    const saved=state.items.length>0;
    const group=(items,preview)=>items.length?preview?`<ul class="zp-preview big">${describeChoices(ctx,items)}</ul>`:items.map(card).join(''):'<p class="zp-none">今天剩余的清醒时段已排满或结束，暂时没有合适的空档。</p>';
    root.innerHTML=`<div class="zp-page"><header class="zp-hero"><div><p>${esc(state.day)} · 校园时间</p><h1>今日规划</h1><p>${esc(historyText(state))}</p></div><span class="zp-orbit" aria-hidden="true"></span></header>
      <div class="zp-board"><div class="zp-heading"><h2>${saved?'我的安排':'今天的空档'}</h2><span>${saved?state.items.filter(i=>i.status==='done').length+' / '+state.items.length+' 已完成':'待采纳'}</span></div>
      <p class="zp-note">安排范围 ${esc(state.window)}。今天${state.classes?'有 '+state.classes+' 项个人课表事务，安排时会避开；课表变动会标记冲突。':'暂无个人课表事务。'} <a href="#campus">查看课表</a></p>
      ${group(saved?state.items:state.suggested,!saved)}<div class="zp-footer">${saved||state.suggested.length?`<button class="zp-primary" data-generate>${saved?'按最新记录重新安排待办':'采用今日规划'}</button>`:''}
      ${saved?'<small>已完成、跳过和手动改时的安排会保留。</small>':''}</div><p role="status" class="zp-alert">${esc(message)}</p></div></div>`;
    const btn=root.querySelector('[data-generate]');if(btn)btn.onclick=()=>update('generate',{},'今日规划已保存。');
    root.querySelectorAll('[data-change]').forEach(b=>b.onclick=()=>{editing=editing===Number(b.dataset.change)?null:Number(b.dataset.change);draw();});
    for(const [attr,status] of [['done','done'],['skip','skipped']])root.querySelectorAll('[data-'+attr+']').forEach(b=>b.onclick=()=>update('status',{id:Number(b.dataset[attr]),status},'已更新。'));
    root.querySelectorAll('[data-form]').forEach(f=>f.onsubmit=e=>{e.preventDefault();update('move',{id:Number(f.dataset.form),time:f.elements.time.value},'已调整时间。');});
  }
  draw();
}
