const moods = { calm:'自在', happy:'开心', curious:'好奇', relaxed:'松弛', sleepy:'困困', listening:'专注' };
const actions = [ ['pat','摸摸头'], ['wave','招招手'], ['stretch','伸懒腰'], ['rest','打个盹'] ];
const sprite = `<span class="zj-specimen" aria-hidden="true"><span class="zj-halo"></span><span class="zj-shadow"></span><span class="zj-friend"><i class="zj-tail"></i><i class="zj-ear left"></i><i class="zj-ear right"></i><i class="zj-leaf"></i><i class="zj-leaf small"></i><i class="zj-foot left"></i><i class="zj-foot right"></i><i class="zj-paw left"></i><i class="zj-paw right"></i><span class="zj-body"><i class="zj-mark"></i><i class="zj-cheek left"></i><i class="zj-cheek right"></i><i class="zj-eye left"></i><i class="zj-eye right"></i><i class="zj-mouth"></i><i class="zj-belly"></i></span></span><i class="zj-spark a">✧</i><i class="zj-spark b">✦</i><i class="zj-snooze">z</i></span>`;


export async function mountPet(root,ctx) {
  const {api,escape:esc}=ctx;
  root.innerHTML=`<div class="zj-pet" data-mood="calm"><section class="zj-pet-drawer" aria-label="桌宠小照" hidden></section><button class="zj-pet-launch" type="button" aria-label="打开桌宠小照" title="点击互动，左右拖动换边" aria-expanded="false">${sprite}<span class="zj-callname">小照</span></button></div>`;
  const pet=root.firstElementChild, drawer=pet.querySelector('section'), launch=pet.querySelector('.zj-pet-launch');
  // A larger companion can sit on either edge, leaving page controls within reach.
  const edgeKey='zj-pet-edge';
  const setEdge=side=>{
    pet.dataset.edge=side==='left'?'left':'right';
    try{localStorage.setItem(edgeKey,pet.dataset.edge);}catch{}
  };
  try{pet.dataset.edge=localStorage.getItem(edgeKey)==='left'?'left':'right';}catch{}
  let drag=null,ignoreClick=false;
  launch.addEventListener('pointerdown',e=>{
    if(e.button!==0)return;
    drag={id:e.pointerId,x:e.clientX,box:launch.getBoundingClientRect(),moved:false};
    launch.setPointerCapture(e.pointerId);
  });
  launch.addEventListener('pointermove',e=>{
    if(!drag||drag.id!==e.pointerId)return;
    const delta=e.clientX-drag.x;
    if(Math.abs(delta)>10)drag.moved=true;
    if(drag.moved){
      const shift=Math.max(6-drag.box.left,Math.min(innerWidth-6-drag.box.right,delta));
      launch.style.translate=shift+'px 0';
    }
  });
  launch.addEventListener('pointerup',e=>{
    if(!drag||drag.id!==e.pointerId)return;
    if(drag.moved){
      setEdge(e.clientX<innerWidth/2?'left':'right');
      ignoreClick=true;setTimeout(()=>{ignoreClick=false;},0);
    }
    launch.style.translate='';drag=null;
  });
  launch.addEventListener('pointercancel',()=>{launch.style.translate='';drag=null;});
  launch.addEventListener('click',e=>{
    if(ignoreClick){e.stopImmediatePropagation();e.preventDefault();}
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
    drawer.innerHTML=`<header class="zj-pet-head"><div><p class="zj-eyebrow">我的桌宠</p><h2>小照 <span data-mood-label>${esc(moods[state.mood]||'自在')}</span></h2></div><div class="pet-tools"><button type="button" data-swap-edge title="把小照移到屏幕另一侧">换边</button><button type="button" class="zj-pet-close" aria-label="收起小照">×</button></div></header><div class="zj-pet-play"><button type="button" data-tickle aria-label="摸摸小照的头">${sprite}</button><div class="zj-pet-gestures">${actions.map(([key,name])=>`<button type="button" data-action="${key}">${name}</button>`).join('')}</div></div><p data-notice role="status"></p><div class="zj-pet-log" role="log" aria-label="与小照的对话" aria-live="polite"></div><form class="zj-pet-compose"><fieldset><legend>陪伴方式</legend>${['倾听','梳理','起步'].map(m=>`<label><input type="radio" name="mode" value="${m}" ${m===mode?'checked':''}><span>${m}</span></label>`).join('')}</fieldset><label class="zj-pet-question"><span>对小照说</span><textarea name="question" maxlength="1000" rows="2" placeholder="今天发生了什么？" required></textarea></label><details class="zj-options"><summary>对话设置</summary>${model?.available?'':`<label><input type="checkbox" name="useAI" ${ai?'checked':''}> 尝试 ${esc(model?.provider||'配置的模型服务')}</label>`}<p>${model?.model?`模型 ${esc(model.model)}。`:''}开启后会发送本次问题、最近三轮对话及本次所选偏好。关闭时使用内置离线陪伴。</p>${state.memories?.length?`<label>本次可用的私人偏好<select name="preference"><option value="">不引用</option>${state.memories.map(m=>`<option value="${m.id}" ${String(m.id)===preference?'selected':''}>${esc(m.note)}</option>`).join('')}</select></label>`:''}<label><input type="checkbox" name="keep" ${state.keep?'checked':''}> 保留最近三轮，供下次接着聊</label><p>默认只在当前页面显示。关闭留存会删除已保存的对话并清空窗口。</p></details>${model?.available?`<p class="zj-ai-hint">AI 发送至${esc(model.provider)}，仅用本次问题、近三轮聊天和所选偏好。</p><div class="zj-send-row"><button type="submit" data-engine="offline">离线发送</button><button class="zj-send" type="submit" data-engine="model">用 AI 回应 <span aria-hidden="true">↗</span></button></div>`:'<button class="zj-send" type="submit">发送 <span aria-hidden="true">↗</span></button>'}</form>`;
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
    if (button.hasAttribute('data-swap-edge')) setEdge(pet.dataset.edge === 'left' ? 'right' : 'left');
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
