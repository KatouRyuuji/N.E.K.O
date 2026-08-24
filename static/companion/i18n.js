// Lightweight i18n for standalone companion static pages (wizard / workshop).
// Loads `companion.*` keys from /static/locales/{lang}.json (8 locales).

(() => {
  'use strict';

  const SUPPORTED = [
    'en', 'ja', 'ko', 'zh-CN', 'zh-TW', 'ru', 'es', 'pt',
  ];

  function normalizeLang(raw) {
    const v = (raw || '').trim();
    if (!v) return 'zh-CN';
    if (SUPPORTED.includes(v)) return v;
    const base = v.split('-')[0];
    if (base === 'zh') {
      return v.toLowerCase().includes('tw') || v.includes('Hant') ? 'zh-TW' : 'zh-CN';
    }
    const hit = SUPPORTED.find((l) => l === base || l.startsWith(base));
    return hit || 'en';
  }

  function detectLang() {
    const params = new URLSearchParams(window.location.search);
    const fromQuery = params.get('lang') || params.get('lng');
    if (fromQuery) return normalizeLang(fromQuery);
    const saved = localStorage.getItem('companionLng');
    if (saved) return normalizeLang(saved);
    return normalizeLang(navigator.language || 'zh-CN');
  }

  let catalog = {};
  let lang = detectLang();

  function t(key, fallback) {
    const parts = key.split('.');
    let node = catalog;
    for (const p of parts) {
      if (!node || typeof node !== 'object') {
        return fallback !== undefined ? fallback : key;
      }
      node = node[p];
    }
    if (typeof node === 'string' && node.length) return node;
    return fallback !== undefined ? fallback : key;
  }

  async function loadCompanionI18n(nextLang) {
    lang = normalizeLang(nextLang || lang);
    localStorage.setItem('companionLng', lang);
    const res = await fetch(`/static/locales/${encodeURIComponent(lang)}.json`);
    if (!res.ok) {
      catalog = {};
      return { lang, t };
    }
    const data = await res.json();
    catalog = data.companion || {};
    document.documentElement.lang = lang;
    return { lang, t };
  }

  window.companionI18n = {
    load: loadCompanionI18n,
    t,
    getLang: () => lang,
    supported: SUPPORTED,
  };
})();
