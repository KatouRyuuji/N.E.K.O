(() => {
  'use strict';

  const API = '/api/companion';

  async function loadCatalog() {
    const res = await fetch(`${API}/workshop/catalog`);
    if (!res.ok) return [];
    const body = await res.json();
    return body.entries || [];
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
      li.innerHTML = `<strong>${entry.display_name || entry.name}</strong>
        <div class="meta">${entry.locale || ''} · ${entry.package_path || ''}</div>`;
      list.append(li);
    }
  });
})();
