/**
 * Companion Live2D Bridge
 *
 * Adapter between the Companion Platform avatar API
 * (/api/companion/avatar/*) and the host page's Live2D runtime.
 *
 * Two host situations are supported:
 *  1. Pages that ship the full N.E.K.O. Live2D stack expose
 *     `window.live2dManager` (see static/live2d/live2d-core.js). The bridge
 *     drives `live2dManager.loadModel(entryUrl, options)` directly for a
 *     true hot swap.
 *  2. Pages without the stack (e.g. the standalone swap panel) receive a
 *     `companion:avatar-swap` CustomEvent on `window` and can react however
 *     they like (iframe postMessage, reload, etc.).
 *
 * No framework dependencies; attach with:
 *   const bridge = new CompanionLive2DBridge();
 */
(function () {
  'use strict';

  const API_BASE = '/api/companion/avatar';
  const SWAP_EVENT = 'companion:avatar-swap';

  async function fetchJson(url, options) {
    const res = await fetch(url, options);
    let payload = null;
    try {
      payload = await res.json();
    } catch (_) {
      /* non-JSON error body */
    }
    if (!res.ok) {
      const detail = payload && payload.detail ? payload.detail : res.statusText;
      const err = new Error(`${res.status} ${detail}`);
      err.status = res.status;
      err.payload = payload;
      throw err;
    }
    return payload;
  }

  class CompanionLive2DBridge {
    /**
     * @param {Object} [opts]
     * @param {Object} [opts.manager] Live2D manager override (defaults to window.live2dManager)
     * @param {Object} [opts.loadOptions] extra options forwarded to loadModel()
     */
    constructor(opts) {
      opts = opts || {};
      this._managerOverride = opts.manager || null;
      this.loadOptions = opts.loadOptions || {};
    }

    get manager() {
      return this._managerOverride || window.live2dManager || null;
    }

    /** Whether a real Live2D runtime is available on this page. */
    hasStage() {
      const m = this.manager;
      return !!(m && typeof m.loadModel === 'function');
    }

    /** GET /avatar/list — all registered avatar profiles. */
    async listAvatars() {
      return fetchJson(`${API_BASE}/list`);
    }

    /** GET /avatar/active — currently active profile (or null). */
    async getActive() {
      const data = await fetchJson(`${API_BASE}/active`);
      return data ? data.active : null;
    }

    /** POST /avatar/load-package — register a `.neko-companion` package. */
    async loadPackage(packagePath, activate) {
      return fetchJson(`${API_BASE}/load-package`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          package_path: packagePath,
          activate: activate !== false,
        }),
      });
    }

    /**
     * POST /avatar/active then apply the model to the local stage.
     * Returns { profile, staged } where staged indicates whether a real
     * Live2D hot swap happened on this page.
     */
    async activate(profileId) {
      const profile = await fetchJson(
        `${API_BASE}/active?profile_id=${encodeURIComponent(profileId)}`,
        { method: 'POST' }
      );
      const staged = await this.applyToStage(profile);
      return { profile, staged };
    }

    /**
     * Drive the host Live2D runtime to display `profile`.
     * Resolves to true when live2dManager performed the swap, false when
     * only the fallback event was dispatched.
     */
    async applyToStage(profile) {
      if (!profile || profile.kind !== 'live2d') {
        this._emitSwapEvent(profile, false, 'unsupported avatar kind');
        return false;
      }
      const entryUrl = profile.entry_url;
      if (!entryUrl) {
        this._emitSwapEvent(profile, false, 'profile has no entry_url');
        return false;
      }
      if (!this.hasStage()) {
        this._emitSwapEvent(profile, false, 'no live2dManager on page');
        return false;
      }
      const manager = this.manager;
      const options = Object.assign(
        {
          isMobile:
            typeof window.isMobileWidth === 'function'
              ? window.isMobileWidth()
              : window.innerWidth <= 768,
        },
        this.loadOptions
      );
      await manager.loadModel(entryUrl, options);
      this._emitSwapEvent(profile, true, null);
      return true;
    }

    _emitSwapEvent(profile, staged, reason) {
      try {
        window.dispatchEvent(
          new CustomEvent(SWAP_EVENT, {
            detail: { profile: profile || null, staged: staged, reason: reason },
          })
        );
      } catch (_) {
        /* CustomEvent unavailable (very old host) — swap still succeeded */
      }
    }
  }

  CompanionLive2DBridge.SWAP_EVENT = SWAP_EVENT;
  window.CompanionLive2DBridge = CompanionLive2DBridge;
})();
