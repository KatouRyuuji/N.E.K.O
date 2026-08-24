(() => {
  'use strict';

  const API = '/api/companion';

  async function loadCatalog() {
    const res = await fetch(`${API}/workshop/catalog`);
    if (!res.ok) return [];
    const body = await res.json();
    return body.entries || [];
  }

  function tagPills(tags) {
    if (!tags || !tags.length) return '';
    return tags.map((t) => `<span class="tag">${t}</span>`).join('');
  }

  window.companionI18n.load().then(async ({ t }) => {
    document.getElementById('title').textContent = t('workshop.title', 'Companion Workshop');
    const list = document.getElementById('catalog');
    const empty = document.getElementById('empty');
    const entries = await loadCatalog();
    if (!entries.length) {
      empty.hidden = false;
      empty.textContent = t('workshop.empty', 'No published companions yet.');
      return;
    }
    for (const entry of entries) {
      const li = document.createElement('li');
      li.className = 'card';
      const cover = entry.cover_url
        ? `<img class="cover" src="${entry.cover_url}" alt="" />`
        : '<div class="cover placeholder"></div>';
      const llm = entry.generator || {};
      const route = llm.model ? `${llm.provider || ''} / ${llm.model}` : '';
      li.innerHTML = `
        ${cover}
        <div class="body">
          <strong>${entry.display_name || entry.name}</strong>
          <div class="tags">${tagPills(entry.tags)}</div>
          <p class="summary">${entry.summary || ''}</p>
          <div class="meta">${entry.locale || ''}${route ? ` · ${route}` : ''}</div>
        </div>`;
      list.append(li);
    }
  });
})();
