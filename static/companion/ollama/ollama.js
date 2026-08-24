// N.E.K.O. Ollama one-click setup (Phase 5 M1)
// Probes the local daemon via GET /api/companion/ai/open-source, lets the
// user pick an installed model, and persists it to provider tiers via
// POST /api/companion/ai/open-source/config.

(() => {
  'use strict';

  const API = '/api/companion';

  const $ = (id) => document.getElementById(id);

  let tr = (key, fallback) => fallback || key;

  function applyStaticI18n() {
    for (const node of document.querySelectorAll('[data-i18n]')) {
      node.textContent = tr(node.dataset.i18n, node.textContent);
    }
  }

  function setProbeState(kind, text) {
    const pill = $('probe-state');
    pill.className = `pill ${kind}`;
    pill.textContent = text;
  }

  function highlightCurrentOs() {
    const ua = (navigator.userAgent || '').toLowerCase();
    let osId = 'os-linux';
    if (ua.includes('mac')) osId = 'os-macos';
    else if (ua.includes('win')) osId = 'os-windows';
    $(osId).classList.add('current');
  }

  function renderModels(models, activeModel) {
    const select = $('model-select');
    select.replaceChildren();
    for (const name of models) {
      const opt = document.createElement('option');
      opt.value = name;
      opt.textContent = name;
      if (name === activeModel) opt.selected = true;
      select.append(opt);
    }
  }

  function renderStatus(status) {
    $('config-card').hidden = true;
    $('install-card').hidden = true;
    if (!status) {
      setProbeState('err', tr('ollama.statusUnavailable', '未检测到本地 Ollama'));
      $('install-card').hidden = false;
      return;
    }
    if (!status.available) {
      const probed = status.providers && status.providers.ollama;
      $('base-url').textContent = (probed && probed.base_url) || '—';
      $('model-count').textContent = '—';
      setProbeState('err', tr('ollama.statusUnavailable', '未检测到本地 Ollama'));
      $('install-card').hidden = false;
      return;
    }
    const models = status.models || [];
    $('base-url').textContent = (status.config && status.config.base_url) || '—';
    $('model-count').textContent = String(models.length);
    setProbeState('ok', tr('ollama.statusAvailable', '已检测到本地 Ollama'));
    $('config-card').hidden = false;
    const hasModels = models.length > 0;
    $('no-models').hidden = hasModels;
    $('model-picker').hidden = !hasModels;
    if (hasModels) {
      renderModels(models, status.config && status.config.model);
    }
  }

  async function probe() {
    setProbeState('busy', tr('ollama.statusChecking', '正在检测…'));
    $('config-card').hidden = true;
    $('install-card').hidden = true;
    try {
      const res = await fetch(`${API}/ai/open-source`);
      renderStatus(res.ok ? await res.json() : null);
    } catch (err) {
      renderStatus(null);
    }
  }

  function selectedTiers() {
    const tiers = [];
    if ($('tier-summary').checked) tiers.push('summary');
    if ($('tier-conversation').checked) tiers.push('conversation');
    return tiers;
  }

  $('apply-btn').addEventListener('click', async () => {
    const out = $('apply-result');
    const model = $('model-select').value;
    const tiers = selectedTiers();
    out.className = '';
    if (!model || !tiers.length) {
      out.className = 'err';
      out.textContent = tr('ollama.applyFailed', '保存失败');
      return;
    }
    const btn = $('apply-btn');
    btn.disabled = true;
    out.textContent = tr('ollama.applying', '保存中…');
    try {
      const res = await fetch(`${API}/ai/open-source/config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model, tiers }),
      });
      const body = await res.json();
      if (!res.ok) {
        out.className = 'err';
        out.textContent = `${tr('ollama.applyFailed', '保存失败')}：${body.detail || res.status}`;
        return;
      }
      out.className = 'ok';
      out.textContent = `${tr('ollama.applied', '已保存，伴侣生成将使用该本地模型')}（${body.config.model}）`;
    } catch (err) {
      out.className = 'err';
      out.textContent = `${tr('ollama.applyFailed', '保存失败')}：${err.message || err}`;
    } finally {
      btn.disabled = false;
    }
  });

  $('recheck-btn').addEventListener('click', probe);

  highlightCurrentOs();
  window.companionI18n.load().then(({ t }) => {
    tr = t;
    applyStaticI18n();
    probe();
  });
})();
