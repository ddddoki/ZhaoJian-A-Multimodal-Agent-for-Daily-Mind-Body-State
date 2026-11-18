import {renderOps} from './ops.js';
import {renderData} from './data.js';
import {renderStudent} from './student.js';
import {renderCampus,renderPrivacy,renderCampusAdmin} from './campus.js';
import {renderManager,renderSharing} from './manager.js';
const app=document.querySelector('#app');
let user=null, demo=false, generation=0;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){
  const response=await fetch(path,data===undefined?{cache:'no-store'}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok){if(response.status===401 && user){user=null;loginPage();}throw new Error(result.error||'请求失败');}
  return result;
}
const brand='<span class="brandmark" aria-hidden="true">☀</span><span>照见<small>ZHAOJIAN</small></span>';
const pet='<div class="mascot" aria-hidden="true"><i></i><b></b><span></span></div>';
function loginPage(){
  app.innerHTML=`<div class="entry"><header class="brand">${brand}</header><main class="welcome"><section class="poster"><div class="poster-title"><h1>给今天的自己，<br>留一点空隙。</h1><p>记录近况，整理课表，和桌宠一起迈出一小步。</p></div><div class="horizon"></div>${pet}<div class="poster-foot">照见 · 校园日常陪伴</div></section><section class="login card"><h2>欢迎来到照见</h2><p>登录后进入自己的工作区。</p><form id="signin"><label>账号<input name="username" autocomplete="username" required></label><label>密码<input name="password" type="password" autocomplete="current-password" required></label><button class="primary">登录</button></form><div id="login-error" class="error" role="alert"></div>${demo?'<div class="demobox"><strong>用虚构账号体验</strong><div class="demochoices"><button data-demo="lin">学生体验 ↗</button><button data-demo="chen">管理体验 ↗</button><button data-demo="ops">运营体验 ↗</button></div><small>体验账号共用，请只填写虚构信息。</small></div>':''}</section></main></div>`;
  async function login(data){try{const result=await api('/api/login',data);user=result.user;location.hash=user.role==='operator'?'ops':user.role==='manager'?'manage':'student';await render();}catch(e){const box=document.querySelector('#login-error');if(box)box.textContent=e.message;}}
  document.querySelector('#signin').onsubmit=e=>{e.preventDefault();login(Object.fromEntries(new FormData(e.target)));};
  app.querySelectorAll('[data-demo]').forEach(b=>b.onclick=()=>login({username:b.dataset.demo,password:'ZhaojianDemo1'}));
}
const pages={ops:['行动库','▤',renderOps],publish:['校园公告','▦',renderCampusAdmin],data:['设备与数据','▧',renderData],student:['学生工作台','◉',renderStudent],campus:['校园日程','▦',renderCampus],sharing:['求助与共享','◇',renderSharing],privacy:['经期与授权','◌',renderPrivacy],manage:['管理工作台','▤',renderManager]};
async function render(){
  if(!user){loginPage();return;}
  const ticket=++generation;
  const keys=user.role==='operator'?['ops']:user.role==='manager'?['manage','publish']:['student','campus','sharing','privacy','data'];
  const selected=keys.includes(location.hash.slice(1))?location.hash.slice(1):keys[0];
  app.innerHTML=`<div class="shell"><aside><div class="brand">${brand}</div><nav aria-label="工作区">${keys.map(k=>`<a href="#${k}" ${k===selected?'aria-current="page"':''}><span aria-hidden="true">${pages[k][1]}</span>${pages[k][0]}</a>`).join('')}</nav><div class="account"><div><strong>${escape(user.name)}</strong><small>${escape(user.cohort)} · ${user.role==='operator'?'运营端':user.role==='manager'?'管理端':'学生'}</small></div><button id="logout">退出</button></div></aside><main class="workspace"><div id="view" aria-live="polite"></div></main></div>`;
  document.querySelector('#logout').onclick=async()=>{try{await api('/api/logout',{});user=null;location.hash='';loginPage();}catch(e){alert(e.message);}};
  const root=document.querySelector('#view');try{await pages[selected][2](root,{api,escape,user,refresh:()=>ticket===generation?render():Promise.resolve(),navigate:k=>{location.hash=k;}});}catch(e){if(ticket===generation&&user){root.innerHTML=`<section class="card"><h2>暂时无法打开这一页</h2><p>${escape(e.message)}</p><button>重新加载</button></section>`;root.querySelector('button').onclick=render;}}
}
window.addEventListener('hashchange',render);
try{const session=await api('/api/session');user=session.user;demo=session.demo;await render();}catch(e){app.textContent='无法连接照见服务，请确认启动窗口仍在运行后刷新。';}
