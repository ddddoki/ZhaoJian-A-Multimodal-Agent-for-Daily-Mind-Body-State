const profiles = {
  student: {name:'学生', demo:'lin', place:'校园日常', tip:'留下此刻的心情，照看自己的校园生活。', display:'怎么称呼你'},
  manager: {name:'管理', demo:'chen', place:'学生支持', tip:'回应学生主动共享的求助，维护班级校园日程。', display:'工作人员姓名'},
  operator: {name:'运营', demo:'ops', place:'内容运营', tip:'编辑陪伴行动、复核发布内容并查看版本记录。', display:'运营人员姓名'}
};

export function renderAuth(root,{api,demo,onLogin,brand}){
  if(!document.querySelector('link[data-auth-style]')){
    const link=document.createElement('link');
    link.rel='stylesheet'; link.href='/auth.css'; link.dataset.authStyle=''; document.head.append(link);
  }
  let role='student';
  let signup=false;
  let pending=false;
  root.innerHTML='<main class="z-auth"><section class="za-image"><div class="za-identity"></div><div class="za-copy"><h1>照见此刻<br>的自己。</h1><p>拍下今天，写下心情。<br>让小照陪你走一段。</p></div></section><section class="za-pane" aria-label="照见账号"><div class="za-content"></div></section></main>';
  const identity=root.querySelector('.za-identity');
  if(brand){identity.innerHTML=brand;}else{identity.textContent='照见';}
  const area=root.querySelector('.za-content');
  async function request(path, body){
    pending=true; area.querySelectorAll('button').forEach(b=>b.disabled=true);
    try{return await api(path,body);}
    finally{pending=false;area.querySelectorAll('button').forEach(b=>b.disabled=false);}
  }
  function showError(err){
    const alert=area.querySelector('[role="alert"]');
    if(alert){alert.textContent=err.message||'暂时无法连接，请稍后再试。';alert.focus();}
  }
  async function loginDemo(){
    if(pending)return;
    try{const result=await request('/api/login',{username:profiles[role].demo,password:'ZhaojianDemo1',role});await onLogin(result.user);}
    catch(err){showError(err);}
  }
  function paint(focus){
    const person=profiles[role];
    const staff=role!=='student';
    area.innerHTML=`<header class="za-heading"><div class="za-headingline"><span class="za-dot" aria-hidden="true"></span> ${person.place}</div><h2>${signup?'创建'+person.name+'账号':'欢迎来到照见'}</h2><p>${person.tip}</p></header>
      <div class="za-roles" role="group" aria-label="选择账号身份">${Object.entries(profiles).map(([value,info])=>`<button type="button" aria-pressed="${value===role}" data-role="${value}">${info.name}端</button>`).join('')}</div>
      <form class="za-form" id="${signup?'signup':'signin'}">
      ${signup?`<label>${person.display}<input name="name" maxlength="60" autocomplete="name" placeholder="${staff?'填写姓名':'填写称呼或昵称'}" required></label>`:''}
      ${signup&&!staff?`<fieldset class="za-gender"><legend>性别</legend><div><label><input type="radio" name="gender" value="female" required>女生</label><label><input type="radio" name="gender" value="male" required>男生</label></div><small>仅自己可见，可在个人资料中更正。</small></fieldset>`:''}
      <label>账号<input name="username" autocomplete="username" spellcheck="false" ${signup?'pattern="[A-Za-z0-9_.\\-]{3,40}" maxlength="40" minlength="3" title="3 至 40 个英文字母、数字、点、短横线或下划线" placeholder="3–40 个英文字母、数字或符号"':'placeholder="输入你的账号"'} required></label>
      <label>密码<input type="password" name="password" autocomplete="${signup?'new-password':'current-password'}" maxlength="256" ${signup?'minlength="10" placeholder="设置至少 10 位密码"':'placeholder="输入密码"'} required></label>
      ${signup&&!staff?'<small>注册后可在班级页面查看并接受老师的入班邀请。</small>':''}
      ${signup&&staff?`<div class="za-invite"><label>${person.name}邀请码<input name="invite" maxlength="128" autocomplete="off" aria-describedby="za-invite-hint" placeholder="输入一次性邀请码" required></label><small id="za-invite-hint">邀请码由项目负责人签发，注册后自动加入对应班级。</small>${demo?'<button class="za-link" type="button" data-invite>填入演示邀请码</button>':''}</div>`:''}
      <div class="za-error" role="alert" tabindex="-1"></div>
      <button class="za-submit" type="submit">${signup?'注册并进入'+person.name+'端':'登录'+person.name+'端'} <span aria-hidden="true">↗</span></button></form>
      <p class="za-switch">${signup?'已有账号？':'第一次使用？'} <button type="button" class="za-link" data-switch>${signup?'返回登录':'注册'+person.name+'账号'}</button></p>
      ${demo&&!signup?`<div class="za-demo"><button type="button" data-demo="${person.demo}">以${person.name}身份体验 <span aria-hidden="true">→</span></button><small>演示账号共用，请填写虚构信息。</small></div>`:''}`;
    area.querySelectorAll('[data-role]').forEach(b=>b.onclick=()=>{if(!pending){role=b.dataset.role;paint('role');}});
    area.querySelector('[data-switch]').onclick=()=>{if(!pending){signup=!signup;paint('form');}};
    area.querySelector('[data-demo]')?.addEventListener('click',loginDemo);
    const form=area.querySelector('form');
    form.onsubmit=async event=>{
      event.preventDefault();if(pending)return;
      const body={...Object.fromEntries(new FormData(form)),role};
      try{const result=await request(signup?'/api/register':'/api/login',body);await onLogin(result.user);}
      catch(err){showError(err);}
    };
    area.querySelector('[data-invite]')?.addEventListener('click',async()=>{
      try{const result=await request('/api/demo/invite',{role});form.elements.invite.value=result.invite;area.querySelector('#za-invite-hint').textContent=`已填入${result.cohort}的一次性演示邀请，一小时内有效。`;}
      catch(err){showError(err);}
    });
    if(focus==='role')area.querySelector('[aria-pressed="true"]').focus();
    if(focus==='form')form.querySelector('input').focus();
  }
  paint();
}
