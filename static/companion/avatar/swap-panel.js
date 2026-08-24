/**
 * Avatar swap panel controller.
 *
 * Lists registered avatar profiles, loads `.neko-companion` packages, and
 * triggers hot swaps through CompanionLive2DBridge. Works standalone (the
 * bridge falls back to a `companion:avatar-swap` event) or embedded in a
 * page that has `window.live2dManager`.
 */
(function () {
  'use strict';

  const bridge = new window.CompanionLive2DBridge();

  const listEl = document.getElementById('avatar-list');
  const statusEl = document.getElementById('swap-status');
  const packageInput = document.getElementById('package-path');
  const loadBtn = document.getElementById('load-package-btn');
  const refreshBtn = document.getElementById('refresh-btn');

  function setStatus(message) {
    statusEl.textContent = message || '';
  }

  function renderEmpty(message) {
    listEl.innerHTML = '';
    const li = document.createElement('li');
    li.className = 'empty';
    li.textContent = message;
    listEl.appendChild(li);
  }

  function renderList(data) {
    listEl.innerHTML = '';
    const profiles = (data && data.profiles) || [];
    if (profiles.length === 0) {
      renderEmpty('还没有注册任何 Avatar，先加载一个伴侣包吧。');
      return;
    }
    profiles.forEach(function (profile) {
      const li = document.createElement('li');
      li.className = 'avatar-item' + (profile.id === data.active_id ? ' active' : '');

      const meta = document.createElement('div');
      meta.className = 'avatar-meta';
      const name = document.createElement('div');
      name.className = 'name';
      name.textContent = profile.display_name || profile.id;
      const slug = document.createElement('div');
      slug.className = 'slug';
      slug.textContent = profile.kind + ' · ' + (profile.slug || profile.resource_id);
      meta.appendChild(name);
      meta.appendChild(slug);

      const btn = document.createElement('button');
      btn.type = 'button';
      if (profile.id === data.active_id) {
        btn.textContent = '当前使用中';
        btn.disabled = true;
      } else {
        btn.textContent = '切换';
        btn.addEventListener('click', function () {
          activateProfile(profile);
        });
      }

      li.appendChild(meta);
      li.appendChild(btn);
      listEl.appendChild(li);
    });
  }

  async function refresh() {
    try {
      const data = await bridge.listAvatars();
      renderList(data);
    } catch (err) {
      renderEmpty('列表加载失败');
      setStatus('刷新失败: ' + err.message);
    }
  }

  async function activateProfile(profile) {
    setStatus('切换中: ' + (profile.display_name || profile.id) + '…');
    try {
      const result = await bridge.activate(profile.id);
      if (result.staged) {
        setStatus('已热替换为 ' + (result.profile.slug || result.profile.id));
      } else {
        setStatus(
          '后端已切换为 ' + (result.profile.slug || result.profile.id) +
          '（本页无 Live2D 舞台，已广播 companion:avatar-swap 事件）'
        );
      }
      await refresh();
    } catch (err) {
      setStatus('切换失败: ' + err.message);
    }
  }

  async function loadPackage() {
    const path = packageInput.value.trim();
    if (!path) {
      setStatus('请先填写伴侣包目录路径。');
      return;
    }
    loadBtn.disabled = true;
    setStatus('加载包中…');
    try {
      const profile = await bridge.loadPackage(path, true);
      setStatus('已加载模型 ' + profile.slug + '（' + profile.entry_url + '）');
      await bridge.applyToStage(profile);
      await refresh();
    } catch (err) {
      setStatus('加载失败: ' + err.message);
    } finally {
      loadBtn.disabled = false;
    }
  }

  loadBtn.addEventListener('click', loadPackage);
  refreshBtn.addEventListener('click', refresh);
  packageInput.addEventListener('keydown', function (e) {
    if (e.key === 'Enter') loadPackage();
  });

  window.addEventListener(window.CompanionLive2DBridge.SWAP_EVENT, function (e) {
    const d = e.detail || {};
    if (d.profile && !d.staged && d.reason) {
      console.info('[swap-panel] avatar swap fallback:', d.reason, d.profile.slug);
    }
  });

  refresh();
})();
