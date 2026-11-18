import {renderPlan} from './planner.js';
import {renderProfile} from './profile.js';
import {renderCareStudent,renderCareManager} from './care.js';
import {renderAuth} from './auth.js';
import {renderJournal} from './journal.js';
import {mountPet} from './pet.js';
import {renderOps} from './ops.js';
import {renderData} from './data.js';
import {renderStudent} from './student.js';
import {renderCampus,renderPrivacy,renderCampusAdmin} from './campus.js';
import {renderManager,renderSharing} from './manager.js';
const app=document.querySelector('#app');
let user=null, demo=false, desktopPet=false, generation=0;
const escape=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function api(path,data){
  const key='zhaojian.tab-session';
  const token=sessionStorage.getItem(key);
  const headers=token?{'X-Zhaojian-Session':token}:{};
  const url=new URL(path,location.origin);
  url.searchParams.set('_request',crypto.randomUUID());
  const options={cache:'no-store',headers};
  if(data!==undefined){
    options.method='POST';
    headers['Content-Type']='application/json';
    options.body=JSON.stringify(data);
  }
  const response=await fetch(url,options);
  const result=await response.json();
  if(!response.ok){
    if(response.status===401 && user && token===sessionStorage.getItem(key)){
      sessionStorage.removeItem(key);user=null;loginPage();
    }
    throw new Error(result.error||'请求失败');
  }
  if(result.tab_session)sessionStorage.setItem(key,result.tab_session);
  if(path==='/api/logout')sessionStorage.removeItem(key);
  return result;
}
const art={sun:'<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2.2 2.2m11.6 11.6L20 20M4 20l2.2-2.2M17.8 6.2 20 4"/>',student:'<path d="m3 11 9-8 9 8v9H3z"/><path d="M9 20v-7h6v7"/>',journal:'<rect x="2" y="6" width="20" height="15" rx="3"/><path d="m6 6 2-3h7l2 3"/><circle cx="12" cy="13" r="4"/>',campus:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 10h18m-14 4h3m3 0h3"/>',sharing:'<path d="M4 5h16v12h-9l-5 4v-4H4z"/><path d="M8 9h8m-8 4h5"/>',privacy:'<rect x="5" y="10" width="14" height="11" rx="3"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/>',data:'<path d="M3 12h4l2-6 4 12 2-6h6"/>',ops:'<path d="M5 4h14v16H5zM8 9h8m-8 4h8m-8 4h5"/>',manage:'<path d="M3 20h18M5 17v-6h3v6m3 0V4h3v13m3 0v-9h3v9"/>',publish:'<path d="m3 10 14-5v14L3 14zm3 5 2 5h3l-2-5m11-6 2-1"/>'};
const icon=k=>`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${art[k]}</svg>`;
const brand=`<span class="brandmark">${icon('sun')}</span><span>照见<small>ZHAOJIAN</small></span>`;
const roleTitle={student:'学生空间',manager:'管理空间',operator:'运营空间'};
Object.assign(art,{
  plan:'<rect x="4" y="3.5" width="16" height="17" rx="3"/><path d="M8 3v3m8-3v3M8 11l1.5 1.5L12 10m2 2h3m-9 4h9"/>',
  care:'<path d="M3 11h4l2-4 3 9 3-6 2 2h4"/><path d="M4 17c2 2 5 3.5 8 5 3-1.5 6-3 8-5"/>',
  profile:'<circle cx="12" cy="8" r="3.6"/><path d="M4 20c.7-4.5 3.4-6.5 8-6.5s7.3 2 8 6.5"/>',
  more:'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>'
});
const pages={
  student:['今日',renderStudent], journal:['照一照 · 心情手记',renderJournal],
  plan:['我的一日规划',renderPlan], campus:['校园日程',renderCampus],
  sharing:['求助与共享',renderSharing], care:['班级与授权',renderCareStudent],
  privacy:['经期与授权',renderPrivacy], profile:['个人资料',renderProfile],
  data:['设备与数据',renderData], ops:['行动库',renderOps], manage:['管理工作台',renderManager],
  roster:['班级与关怀',renderCareManager],publish:['校园公告',renderCampusAdmin]
};
art.roster=art.care;
const compact={student:'今日',journal:'照一照',plan:'规划',campus:'校园',manage:'工作台',roster:'班级',publish:'公告',ops:'行动库'};
let petOwner=null;
function groupsFor(account){
  if(account.role==='manager')return [['班级工作',['manage','roster','publish']]];
  if(account.role==='operator')return [['内容运营',['ops']]];
  const mine=['care','sharing','data'];
  if(account.gender==='female')mine.push('privacy');
  mine.push('profile');
  return [['日常',['student','journal','plan','campus']],['我的空间',mine]];
}
function loginPage(){
  document.querySelector('#pet-layer')?.replaceChildren();petOwner=null;
  renderAuth(app,{api,demo,brand,onLogin:async logged=>{
    user=logged;
    const first={operator:'ops',manager:'manage',student:'student'}[user.role];
    history.replaceState(null,'','#'+first);
    await render();
  }});
}
async function reloadUser(){
  const session=await api('/api/session');
  user=session.user;demo=session.demo;desktopPet=session.desktop_pet===true;
  await render();
}
function navLink(key,selected,short=false){
  return `<a href="#${key}" ${key===selected?'aria-current="page"':''}>${icon(key)}<span class="nav-name">${short?compact[key]:pages[key][0]}</span></a>`;
}
async function render(){
  if(!user){loginPage();return;}
  const ticket=++generation,groups=groupsFor(user),keys=groups.flatMap(([,items])=>items);
  const wanted=location.hash.slice(1);
  const selected=keys.includes(wanted)?wanted:keys[0];
  if(wanted!==selected)history.replaceState(null,'','#'+selected);
  const shortcuts=groups[0][1];
  const hasMore=keys.length>shortcuts.length;
  const date=new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'});
  const groupHTML=groups.map(([name,items])=>`<div class="nav-group"><div class="group-title">${name}</div>${items.map(key=>navLink(key,selected)).join('')}</div>`).join('');
  const who=`<strong>${escape(user.name)}</strong><small>${escape(user.cohort)||'尚未加入班级'}</small>`;
  app.innerHTML=`<div class="shell" data-role="${user.role}">
    <aside class="sidebar"><div class="brand">${brand}</div><nav class="side-links" aria-label="工作区">${groupHTML}</nav>
    <div class="account"><span class="avatar" aria-hidden="true">${escape(Array.from(user.name||'照')[0])}</span><div class="account-name">${who}</div><button data-logout>退出</button></div></aside>
    <main class="workspace"><header class="workspace-head"><span><i class="live-dot" aria-hidden="true"></i>${roleTitle[user.role]}<span class="crumb-sep" aria-hidden="true">/</span><b>${pages[selected][0]}</b></span><time>${date}</time></header><div id="view"></div></main>
    <nav class="tabbar" aria-label="快捷导航">${shortcuts.map(key=>navLink(key,selected,true)).join('')}${hasMore?`<button id="nav-more" aria-haspopup="dialog" aria-controls="space-menu">${icon('more')}<span>更多</span></button>`:''}</nav>
    ${hasMore?`<dialog id="space-menu" aria-label="我的空间"><div class="sheet-head"><h2>我的空间</h2><button data-close aria-label="关闭菜单">×</button></div><div class="more-links">${groups[1][1].map(key=>navLink(key,selected)).join('')}</div></dialog>`:''}
    </div>`;
  const sheet=app.querySelector('#space-menu');
  if(sheet){
    const more=app.querySelector('#nav-more');
    if(!shortcuts.includes(selected))more.classList.add('selected');
    more.onclick=()=>sheet.showModal();
    sheet.querySelector('[data-close]').onclick=()=>sheet.close();
    sheet.addEventListener('click',event=>{if(event.target===sheet||event.target.closest('a'))sheet.close();});
  }
  app.querySelector('[data-logout]').onclick=async()=>{
    try{await api('/api/logout',{});user=null;history.replaceState(null,'',location.pathname);loginPage();}
    catch(e){alert(e.message);}
  };
  const root=app.querySelector('#view');
  const ctx={api,escape,user,reloadUser,desktopPet,refresh:()=>ticket===generation?render():Promise.resolve(),navigate:key=>{location.hash=key;}};
  const layer=document.querySelector('#pet-layer');
  if(user.role==='student'&&petOwner!==user.id){
    petOwner=user.id;
    const mount=document.createElement('div');layer.replaceChildren(mount);
    mountPet(mount,ctx).catch(()=>{petOwner=null;});
  }else if(user.role!=='student'){
    layer.replaceChildren();petOwner=null;
  }
  try{await pages[selected][1](root,ctx);}
  catch(e){
    if(ticket===generation&&user){
      root.innerHTML=`<section class="card"><h2>暂时无法打开这一页</h2><p>${escape(e.message)}</p><button>重新加载</button></section>`;
      root.querySelector('button').onclick=render;
    }
  }
}
window.addEventListener('hashchange',()=>{window.scrollTo(0,0);render();});
try{await reloadUser();}
catch(e){app.textContent='无法连接照见服务，请确认启动窗口仍在运行后刷新。';}
