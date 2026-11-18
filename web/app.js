import {renderAuth} from './auth.js';
import {renderJournal} from './journal.js';
import {mountPet} from './pet.js';
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
const art={sun:'<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2.2 2.2m11.6 11.6L20 20M4 20l2.2-2.2M17.8 6.2 20 4"/>',student:'<path d="m3 11 9-8 9 8v9H3z"/><path d="M9 20v-7h6v7"/>',journal:'<rect x="2" y="6" width="20" height="15" rx="3"/><path d="m6 6 2-3h7l2 3"/><circle cx="12" cy="13" r="4"/>',campus:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 10h18m-14 4h3m3 0h3"/>',sharing:'<path d="M4 5h16v12h-9l-5 4v-4H4z"/><path d="M8 9h8m-8 4h5"/>',privacy:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',data:'<path d="M3 12h4l2-6 4 12 2-6h6"/>',ops:'<path d="M5 4h14v16H5zM8 9h8m-8 4h8m-8 4h5"/>',manage:'<path d="M3 20h18M5 17v-6h3v6m3 0V4h3v13m3 0v-9h3v9"/>',publish:'<path d="m3 10 14-5v14L3 14zm3 5 2 5h3l-2-5m11-6 2-1"/>'};
const icon=k=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${art[k]}</svg>`;
const brand=`<span class="brandmark">${icon('sun')}</span><span>照见<small>ZHAOJIAN</small></span>`;
const roleTitle={student:'学生空间',manager:'管理空间',operator:'运营空间'};
const pages={student:['今日',renderStudent],journal:['照一照 · 心情手记',renderJournal],campus:['校园日程',renderCampus],sharing:['求助与共享',renderSharing],privacy:['经期与授权',renderPrivacy],data:['设备与数据',renderData],ops:['行动库',renderOps],manage:['管理工作台',renderManager],publish:['校园公告',renderCampusAdmin]};
let petOwner=null;
function loginPage(){
  document.querySelector('#pet-layer')?.replaceChildren();petOwner=null;
  renderAuth(app,{api,demo,brand,onLogin:async logged=>{user=logged;const first={operator:'ops',manager:'manage',student:'student'}[user.role];history.replaceState(null,'','#'+first);await render();}});
}
async function render(){
  if(!user){loginPage();return;}
  const ticket=++generation;
  const keys=user.role==='operator'?['ops']:user.role==='manager'?['manage','publish']:['student','journal','campus','sharing','privacy','data'];
  const selected=keys.includes(location.hash.slice(1))?location.hash.slice(1):keys[0];
  app.innerHTML=`<div class="shell"><aside><div class="brand">${brand}</div><nav aria-label="工作区">${keys.map(k=>`<a href="#${k}" ${k===selected?'aria-current="page"':''}>${icon(k)}${pages[k][0]}</a>`).join('')}</nav><div class="account"><div><strong>${escape(user.name)}</strong><small>${escape(user.cohort)} · ${user.role==='operator'?'运营端':user.role==='manager'?'管理端':'学生'}</small></div><button id="logout">退出</button></div></aside><main class="workspace"><div class="workspace-head"><span>${roleTitle[user.role]}　/　<b>${pages[selected][0]}</b></span><time>${new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})}</time></div><div id="view" aria-live="polite"></div></main></div>`;
  document.querySelector('#logout').onclick=async()=>{try{await api('/api/logout',{});user=null;location.hash='';loginPage();}catch(e){alert(e.message);}};
  const root=document.querySelector('#view');const ctx={api,escape,user,refresh:()=>ticket===generation?render():Promise.resolve(),navigate:k=>{location.hash=k;}};const layer=document.querySelector('#pet-layer');if(user.role==='student'&&petOwner!==user.id){petOwner=user.id;const mount=document.createElement('div');layer.replaceChildren(mount);mountPet(mount,ctx).catch(()=>{petOwner=null;});}else if(user.role!=='student'){layer.replaceChildren();petOwner=null;}try{await pages[selected][1](root,ctx);}catch(e){if(ticket===generation&&user){root.innerHTML=`<section class="card"><h2>暂时无法打开这一页</h2><p>${escape(e.message)}</p><button>重新加载</button></section>`;root.querySelector('button').onclick=render;}}
}
window.addEventListener('hashchange',render);
try{const session=await api('/api/session');user=session.user;demo=session.demo;await render();}catch(e){app.textContent='无法连接照见服务，请确认启动窗口仍在运行后刷新。';}
