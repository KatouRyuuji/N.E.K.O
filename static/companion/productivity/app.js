// N.E.K.O. Companion Productivity Panel
// Talks to /api/companion/productivity/* (todos + memos persisted via SQLite)
// and the read-only music router state endpoint.

(() => {
  'use strict';

  const API = '/api/companion/productivity';
  const POLL_MS = 15000;

  const $ = (id) => document.getElementById(id);
  const connState = $('conn-state');

  let state = { pomodoro: null, todos: [], memos: [] };
  let tickTimer = null;

  // ---------------------------------------------------------------- helpers

  async function api(path, options = {}) {
    const res = await fetch(API + path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => '');
      throw new Error(`HTTP ${res.status} ${detail}`.trim());
    }
    return res.json();
  }

  function setConnected(ok, message) {
    connState.className = ok ? 'ok' : 'err';
    connState.textContent = message || (ok ? '已连接' : '连接失败');
  }

  function fmtTime(totalSeconds) {
    const s = Math.max(0, Math.floor(totalSeconds));
    const mm = String(Math.floor(s / 60)).padStart(2, '0');
    const ss = String(s % 60).padStart(2, '0');
    return `${mm}:${ss}`;
  }

  function fmtDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString('zh-CN', { hour12: false });
  }

  function el(tag, props = {}, children = []) {
    const node = document.createElement(tag);
    Object.assign(node, props);
    for (const child of children) node.append(child);
    return node;
  }

  // --------------------------------------------------------------- pomodoro

  const PHASE_LABEL = { idle: '待机', work: '专注中', break: '休息中' };

  function renderPomodoro() {
    const p = state.pomodoro;
    if (!p) return;
    $('pomo-config').textContent = `${p.work_minutes}分专注 / ${p.break_minutes}分休息`;
    const phaseEl = $('pomo-phase');
    phaseEl.dataset.phase = p.phase;
    phaseEl.textContent = PHASE_LABEL[p.phase] || p.phase;
    $('pomo-cycles').textContent = p.completed_cycles
      ? `已完成 ${p.completed_cycles} 个番茄`
      : '';
    tickPomodoro();
  }

  function tickPomodoro() {
    const p = state.pomodoro;
    const timeEl = $('pomo-time');
    if (!p || p.phase === 'idle' || !p.started_at) {
      timeEl.textContent = '--:--';
      return;
    }
    const total = (p.phase === 'work' ? p.work_minutes : p.break_minutes) * 60;
    const elapsed = (Date.now() - new Date(p.started_at).getTime()) / 1000;
    timeEl.textContent = fmtTime(total - elapsed);
  }

  async function pomodoroAction(path) {
    try {
      const data = await api(path, { method: 'POST' });
      if (data.pomodoro) {
        state.pomodoro = data.pomodoro;
        renderPomodoro();
      }
      setConnected(true);
    } catch (err) {
      setConnected(false, `操作失败：${err.message}`);
    }
  }

  $('pomo-work').addEventListener('click', () => pomodoroAction('/pomodoro/start?phase=work'));
  $('pomo-break').addEventListener('click', () => pomodoroAction('/pomodoro/start?phase=break'));
  $('pomo-stop').addEventListener('click', () => pomodoroAction('/pomodoro/stop'));

  // ------------------------------------------------------------------ todos

  function renderTodos() {
    const list = $('todo-list');
    list.replaceChildren();
    const remaining = state.todos.filter((t) => !t.done).length;
    $('todo-count').textContent = state.todos.length
      ? `${remaining} 项未完成 / 共 ${state.todos.length} 项`
      : '';
    if (!state.todos.length) {
      list.append(el('div', { className: 'empty', textContent: '暂无待办，添加一条吧' }));
      return;
    }
    for (const todo of state.todos) {
      const checkbox = el('input', { type: 'checkbox', checked: todo.done });
      checkbox.addEventListener('change', () => toggleTodo(todo.id, checkbox.checked));
      const delBtn = el('button', { className: 'del', title: '删除', textContent: '×' });
      delBtn.addEventListener('click', () => deleteTodo(todo.id));
      list.append(
        el('li', { className: `item${todo.done ? ' done' : ''}` }, [
          checkbox,
          el('div', { className: 'body' }, [
            el('div', { className: 'title', textContent: todo.title }),
            el('div', { className: 'meta', textContent: fmtDate(todo.created_at) }),
          ]),
          delBtn,
        ]),
      );
    }
  }

  async function toggleTodo(id, done) {
    try {
      const updated = await api(`/todos/${id}`, {
        method: 'PATCH',
        body: JSON.stringify({ done }),
      });
      state.todos = state.todos.map((t) => (t.id === id ? updated : t));
      renderTodos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `操作失败：${err.message}`);
      refresh();
    }
  }

  async function deleteTodo(id) {
    try {
      await api(`/todos/${id}`, { method: 'DELETE' });
      state.todos = state.todos.filter((t) => t.id !== id);
      renderTodos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `操作失败：${err.message}`);
      refresh();
    }
  }

  $('todo-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('todo-input');
    const title = input.value.trim();
    if (!title) return;
    try {
      const created = await api('/todos', {
        method: 'POST',
        body: JSON.stringify({ title }),
      });
      state.todos.push(created);
      input.value = '';
      renderTodos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `添加失败：${err.message}`);
    }
  });

  // ------------------------------------------------------------------ memos

  function renderMemos() {
    const list = $('memo-list');
    list.replaceChildren();
    $('memo-count').textContent = state.memos.length ? `${state.memos.length} 条` : '';
    if (!state.memos.length) {
      list.append(el('div', { className: 'empty', textContent: '暂无备忘' }));
      return;
    }
    for (const memo of state.memos) {
      const delBtn = el('button', { className: 'del', title: '删除', textContent: '×' });
      delBtn.addEventListener('click', () => deleteMemo(memo.id));
      list.append(
        el('li', { className: 'item' }, [
          el('div', { className: 'body' }, [
            el('div', { className: 'title', textContent: memo.content }),
            el('div', { className: 'meta', textContent: fmtDate(memo.created_at) }),
          ]),
          delBtn,
        ]),
      );
    }
  }

  async function deleteMemo(id) {
    try {
      await api(`/memos/${id}`, { method: 'DELETE' });
      state.memos = state.memos.filter((m) => m.id !== id);
      renderMemos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `操作失败：${err.message}`);
      refresh();
    }
  }

  $('memo-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const input = $('memo-input');
    const content = input.value.trim();
    if (!content) return;
    try {
      const created = await api('/memos', {
        method: 'POST',
        body: JSON.stringify({ content }),
      });
      state.memos.unshift(created);
      input.value = '';
      renderMemos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `保存失败：${err.message}`);
    }
  });

  // ------------------------------------------------------------------ music

  function pill(stateName, text) {
    return el('span', { className: `pill ${stateName}`, textContent: text });
  }

  function renderMusic(music) {
    const body = $('music-body');
    body.replaceChildren();
    if (!music || !music.available) {
      body.append(
        el('div', { className: 'kv' }, [
          el('span', { className: 'k', textContent: '服务状态' }),
          el('span', { className: 'v' }, [pill('off', '不可用')]),
        ]),
        el('div', {
          className: 'empty',
          textContent: (music && music.reason) || '音乐路由未加载',
        }),
      );
      return;
    }
    const cache = music.proxy_cache || {};
    const vip = music.netease_vip_resolver;
    const vipPill =
      vip === true ? pill('on', '可用')
      : vip === false ? pill('off', '不可用')
      : pill('na', '未初始化');
    const rows = [
      ['服务状态', [pill('on', '在线')]],
      ['网易云 VIP 解析', [vipPill]],
      ['代理缓存条目', [String(cache.entries ?? '—')]],
      [
        '缓存占用',
        [
          cache.current_size != null && cache.max_size != null
            ? `${(cache.current_size / 1048576).toFixed(1)} / ${(cache.max_size / 1048576).toFixed(0)} MB`
            : '—',
        ],
      ],
      ['音源域名', [String((music.source_domains || []).length) + ' 个']],
    ];
    for (const [k, v] of rows) {
      body.append(
        el('div', { className: 'kv' }, [
          el('span', { className: 'k', textContent: k }),
          el('span', { className: 'v' }, v),
        ]),
      );
    }
    if ((music.source_domains || []).length) {
      body.append(
        el('div', { id: 'music-domains', textContent: music.source_domains.join(' · ') }),
      );
    }
  }

  // ---------------------------------------------------------------- refresh

  async function refresh() {
    try {
      const status = await api('/status');
      state.pomodoro = status.pomodoro;
      state.todos = status.todos || [];
      state.memos = status.memos || [];
      renderPomodoro();
      renderTodos();
      renderMemos();
      setConnected(true);
    } catch (err) {
      setConnected(false, `无法连接：${err.message}`);
    }
    try {
      renderMusic(await api('/music'));
    } catch (err) {
      renderMusic({ available: false, reason: err.message });
    }
  }

  refresh();
  setInterval(refresh, POLL_MS);
  tickTimer = setInterval(tickPomodoro, 1000);
  void tickTimer;
})();
