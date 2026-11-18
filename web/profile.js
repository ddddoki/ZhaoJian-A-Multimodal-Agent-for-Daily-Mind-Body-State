export async function renderProfile(root, ctx) {
  if (!document.querySelector('link[data-profile-style]')) {
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = '/profile.css';
    link.dataset.profileStyle = '';
    document.head.append(link);
  }
  const {user, api, escape: esc} = ctx;
  const profile = await api('/api/profile');
  const known = ['female', 'male'].includes(user.gender);
  const options = [['female', '女生'], ['male', '男生']];
  root.innerHTML = `<div class="profile-page">
    <section class="card"><h1>个人资料</h1><p>${esc(user.name)} · ${esc(user.username)}</p>
    <form><fieldset class="profile-options"><legend>性别</legend>
    ${options.map(([value,label])=>`<label><input type="radio" name="gender" value="${value}" ${user.gender===value?'checked':''} required> ${label}</label>`).join('')}</fieldset>
    <p class="muted">${known?'仅自己可见。更正资料后，经期记录需要重新授权。':'请由本人补全学生资料。女生可以在经期与授权页单独决定是否开始记录。'}</p>
    <button type="submit" class="primary">保存资料</button></form><p role="status"></p></section>
    ${profile.has_cycle_history?'<details class="card"><summary>清除个人历史健康记录</summary><p>将删除本人保存的全部经期记录与经期授权。删除后无法恢复。</p><button type="button" data-clear>清除历史经期记录</button></details>':''}</div>`;
  const form = root.querySelector('form');
  const status = root.querySelector('[role="status"]');
  form.onsubmit = async e => {
    e.preventDefault();
    const button = form.querySelector('button');
    const gender = new FormData(form).get('gender');
    button.disabled = true;
    try {
      await api('/api/profile/gender', {gender});
      await ctx.reloadUser();
      const latest = document.querySelector('.profile-page [role="status"]');
      if (latest) latest.textContent = '资料已保存。';
    } catch (error) {status.textContent = error.message;}
    finally {button.disabled = false;}
  };
  const clear = root.querySelector('[data-clear]');
  if (!clear) return;
  clear.onclick = async () => {
    if (!window.confirm('确认永久清除你的全部历史经期记录与授权？')) return;
    clear.disabled = true;
    try {
      await api('/api/profile/clear-cycle', {confirm:true});
      clear.closest('details').remove();
      status.textContent = '历史经期记录与授权已清除。';
    } catch (error) {status.textContent = error.message;}
    finally {clear.disabled = false;}
  };
}
