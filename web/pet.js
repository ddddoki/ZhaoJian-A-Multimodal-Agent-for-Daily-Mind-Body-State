const moods = { calm:'自在', happy:'开心', curious:'好奇', relaxed:'松弛', sleepy:'困困', listening:'专注' };
const actions = [ ['pat','摸摸头'], ['wave','招招手'], ['stretch','伸懒腰'], ['rest','打个盹'] ];
const sprite = `<span class="zj-specimen" aria-hidden="true"><span class="zj-halo"></span><span class="zj-shadow"></span><span class="zj-friend"><i class="zj-tail"></i><i class="zj-ear left"></i><i class="zj-ear right"></i><i class="zj-leaf"></i><i class="zj-leaf small"></i><i class="zj-foot left"></i><i class="zj-foot right"></i><i class="zj-paw left"></i><i class="zj-paw right"></i><span class="zj-body"><i class="zj-mark"></i><i class="zj-cheek left"></i><i class="zj-cheek right"></i><i class="zj-eye left"></i><i class="zj-eye right"></i><i class="zj-mouth"></i><i class="zj-belly"></i></span></span><i class="zj-spark a">✧</i><i class="zj-spark b">✦</i><i class="zj-snooze">z</i></span>`;


export async function mountPet(root,ctx) {
  const {api,escape:esc}=ctx;
  root.innerHTML=`<div class="zj-pet" data-mood="calm"><section class="zj-pet-drawer" aria-label="桌宠小照" hidden></section><button class="zj-pet-launch" type="button" aria-label="打开桌宠小照" title="轻点互动，按住可自由拖动" aria-expanded="false">${sprite}<span class="zj-callname">小照</span></button></div>`;
  const pet=root.firstElementChild, drawer=pet.querySelector('section'), launch=pet.querySelector('.zj-pet-launch');
  // Fractions refer to the available travel after subtracting the widget size.
  // The launcher and the larger open drawer use the same anchor within their own travel.
  const positionKey='zj-pet-position';
  const clamp=value=>Math.max(0,Math.min(1,value));
  let position={x:1,y:1};
  try{
    const saved=JSON.parse(localStorage.getItem(positionKey));
    if(Number.isFinite(saved?.x)&&Number.isFinite(saved?.y)){
      position={x:clamp(saved.x),y:clamp(saved.y)};
    }else if(localStorage.getItem('zj-pet-edge')==='left'){
      position.x=0;
    }
  }catch{}
  function place(x,y){
    position={x:clamp(x),y:clamp(y)};
    pet.style.setProperty('--pet-x',position.x);
    pet.style.setProperty('--pet-y',position.y);
    pet.dataset.edge=position.x<0.5?'left':'right';
  }
  function remember(){
    try{localStorage.setItem(positionKey,JSON.stringify(position));}catch{}
  }
  place(position.x,position.y);
  let drag=null,suppressClick=false;
  launch.addEventListener('pointerdown',e=>{
    if(!e.isPrimary||e.button!==0||drag)return;
    const box=launch.getBoundingClientRect();
    drag={id:e.pointerId,startX:e.clientX,startY:e.clientY,offsetX:e.clientX-box.left,
          offsetY:e.clientY-box.top,original:position,moved:false};
    suppressClick=false;
    launch.setPointerCapture(e.pointerId);
  });
  function move(e){
    if(!drag||drag.id!==e.pointerId)return;
    if(!drag.moved&&Math.hypot(e.clientX-drag.startX,e.clientY-drag.startY)<7)return;
    drag.moved=true;
    launch.classList.add('is-dragging');
    const area=pet.getBoundingClientRect(),box=launch.getBoundingClientRect();
    const width=area.width-box.width,height=area.height-box.height;
    place(width>0?(e.clientX-area.left-drag.offsetX)/width:0,
          height>0?(e.clientY-area.top-drag.offsetY)/height:0);
  }
  launch.addEventListener('pointermove',move);
  launch.addEventListener('pointerup',e=>{
    if(!drag||drag.id!==e.pointerId)return;
    move(e);
    if(drag.moved){remember();suppressClick=true;}
    drag=null;
    launch.classList.remove('is-dragging');
  });
  function cancelDrag(e){
    if(!drag||drag.id!==e.pointerId)return;
    place(drag.original.x,drag.original.y);
    drag=null;
    launch.classList.remove('is-dragging');
  }
  launch.addEventListener('pointercancel',cancelDrag);
  launch.addEventListener('lostpointercapture',cancelDrag);
  launch.addEventListener('click',e=>{
    // Touch browsers can dispatch this click after pointerup in a later task.
    if(suppressClick&&e.detail>0){e.stopImmediatePropagation();e.preventDefault();}
    suppressClick=false;
  },true);
  let state={mood:'calm',keep:false,memories:[]}, model=null, chat=[], busy=false, mode='倾听', firstLoad=true, loaded=false;
  let ai=false, preference='',animTimer, version=0;
  const req=(op,data)=>api('/api/pet'+(op?'/'+op:''),data);
  const notice=text=>{const node=drawer.querySelector('[data-notice]');if(node)node.textContent=text;};
  function applyState(result){state={...state,...result};pet.dataset.mood=state.mood;const label=drawer.querySelector('[data-mood-label]');if(label)label.textContent=moods[state.mood]||'自在';}
  function animate(action){clearTimeout(animTimer);delete pet.dataset.motion;void pet.offsetWidth;pet.dataset.motion=action;animTimer=setTimeout(()=>delete pet.dataset.motion,1400);}
  function previousTurns(){return chat.slice(-3).flatMap(t=>[{role:'user',content:t.question},{role:'assistant',content:t.answer}]);}
  function renderChat(){const log=drawer.querySelector('.zj-pet-log');if(!log)return;log.innerHTML=chat.length?chat.map(t=>`<div class="zj-line mine"><span>我</span><p>${esc(t.question)}</p></div><div class="zj-line"><span>小照 · ${esc(t.source)}</span><p>${esc(t.answer)}</p>${t.urgent?'<a href="#sharing">去求助与共享 →</a>':''}</div>`).join(''):'<p class="zj-intro">我在。你可以从今天一个很小的瞬间说起。</p>';log.scrollTop=log.scrollHeight;}
  function show(){
    drawer.innerHTML=`<header class="zj-pet-head"><div><p class="zj-eyebrow">我的桌宠</p><h2>小照 <span data-mood-label>${esc(moods[state.mood]||'自在')}</span></h2></div><div class="pet-tools">${ctx.desktopPet?'<button type="button" data-open-desktop title="打开独立的 Windows 桌面小照">放到桌面</button>':''}<button type="button" data-swap-edge title="把小照移到屏幕另一侧">换边</button><button type="button" class="zj-pet-close" aria-label="收起小照">×</button></div></header><div class="zj-pet-play"><button type="button" data-tickle aria-label="摸摸小照的头">${sprite}</button><div class="zj-pet-gestures">${actions.map(([key,name])=>`<button type="button" data-action="${key}">${name}</button>`).join('')}</div></div><p data-notice role="status"></p><div class="zj-pet-log" role="log" aria-label="与小照的对话" aria-live="polite"></div><form class="zj-pet-compose"><fieldset><legend>陪伴方式</legend>${['倾听','梳理','起步'].map(m=>`<label><input type="radio" name="mode" value="${m}" ${m===mode?'checked':''}><span>${m}</span></label>`).join('')}</fieldset><label class="zj-pet-question"><span>对小照说</span><textarea name="question" maxlength="1000" rows="2" placeholder="今天发生了什么？" required></textarea></label><details class="zj-options"><summary>对话设置</summary>${model?.available?'':`<label><input type="checkbox" name="useAI" ${ai?'checked':''}> 尝试 ${esc(model?.provider||'配置的模型服务')}</label>`}<p>${model?.model?`模型 ${esc(model.model)}。`:''}开启后会发送本次问题、最近三轮对话及本次所选偏好。关闭时使用内置离线陪伴。</p>${state.memories?.length?`<label>本次可用的私人偏好<select name="preference"><option value="">不引用</option>${state.memories.map(m=>`<option value="${m.id}" ${String(m.id)===preference?'selected':''}>${esc(m.note)}</option>`).join('')}</select></label>`:''}<label><input type="checkbox" name="keep" ${state.keep?'checked':''}> 保留最近三轮，供下次接着聊</label><p>默认只在当前页面显示。关闭留存会删除已保存的对话并清空窗口。</p></details>${model?.available?`<p class="zj-ai-hint">AI 发送至${esc(model.provider)}，仅用本次问题、近三轮聊天和所选偏好。</p><div class="zj-send-row"><button type="submit" data-engine="offline">离线发送</button><button class="zj-send" type="submit" data-engine="model">用 AI 回应 <span aria-hidden="true">↗</span></button></div>`:'<button class="zj-send" type="submit">发送 <span aria-hidden="true">↗</span></button>'}</form>`;
    renderChat();
  }
  function opened(value){drawer.hidden=!value;launch.setAttribute('aria-expanded',String(value));launch.setAttribute('aria-label',value?'收起小照':'打开桌宠小照');pet.classList.toggle('zj-open',value);if(value){show();drawer.querySelector('.zj-pet-close').focus({preventScroll:true});}else{launch.focus({preventScroll:true});}}
  async function sync(){
    const seq=++version; const [s,config]=await Promise.all([req(''),api('/api/ai/status').catch(()=>({text:null}))]);
    if(seq!==version||!pet.isConnected)return;loaded=true;applyState(s);model=config.text;
    if(firstLoad){if(s.keep)chat=s.turns||[];firstLoad=false;}
    if(!drawer.hidden)show();
  }
  launch.onclick=async()=>{if(!drawer.hidden){opened(false);return;}opened(true);if(!loaded){notice('正在连接小照…');try{await sync();}catch(e){notice(e.message);}}};
  function working(value){busy=value;for(const btn of drawer.querySelectorAll('button:not(.zj-pet-close),input,select,textarea'))btn.disabled=value;}
  async function perform(action){if(busy)return;working(true);try{const s=await req('interact',{action});if(!pet.isConnected)return;applyState(s);animate(action);notice(s.caption);}catch(e){notice(e.message);}finally{working(false);}}
  drawer.addEventListener('click', event => {
    const button = event.target.closest('button');
    if (!button || !drawer.contains(button)) return;
    if (button.hasAttribute('data-open-desktop')) {
      button.disabled=true;
      notice('正在打开 Windows 桌面小照…');
      api('/api/desktop/start',{}).then(result=>{
        notice(result.already_running?'桌面小照已经打开。':'桌面小照已打开。可以最小化网页，点击小照继续聊天。');
      }).catch(error=>notice(error.message)).finally(()=>{button.disabled=false;});
    } else if (button.hasAttribute('data-swap-edge')) {
      place(position.x<0.5?1:0,position.y);
      remember();
    }
    else if (button.classList.contains('zj-pet-close')) opened(false);
    else if (button.hasAttribute('data-tickle')) perform('pat');
    else if (button.hasAttribute('data-action')) perform(button.dataset.action);
  });
  drawer.addEventListener('change',async e=>{const field=e.target;if(field.name==='mode')mode=field.value;if(field.name==='useAI')ai=field.checked;if(field.name==='preference')preference=field.value;
    if(field.name==='keep'&&!busy){working(true);try{const s=await req('retention',{keep:field.checked});applyState(s);if(!state.keep){chat=[];renderChat();}notice(state.keep?'接下来只保存最近三轮。':'已清除留存对话。');}catch(err){field.checked=state.keep;notice(err.message);}finally{working(false);}}});
  drawer.addEventListener('submit',async e=>{e.preventDefault();if(busy)return;const field=drawer.querySelector('textarea');const question=field.value.trim();if(!question){field.focus();return;}
    const engine=e.submitter?.dataset.engine;const useAI=engine?engine==='model':ai;working(true);notice(useAI?'正在等待模型回应…':'小照在听…');try{const s=await req('chat',{text:question,mode,use_ai:useAI,memory_id:preference?Number(preference):null,history:previousTurns()});if(!pet.isConnected)return;applyState(s);chat=[...chat,{question,answer:s.text,source:s.source,urgent:s.urgent}].slice(-12);renderChat();field.value='';animate('listen');notice('');}catch(err){notice(err.message);}finally{working(false);if(pet.isConnected&&!drawer.hidden)field.focus({preventScroll:true});}});
  root.addEventListener('keydown',e=>{if(e.key==='Escape'&&!drawer.hidden){e.preventDefault();opened(false);}});
  try{await sync();}catch(e){loaded=false;if(!drawer.hidden)notice(e.message);}
}
