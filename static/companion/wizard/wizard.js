// N.E.K.O. Companion Generation Wizard
// Posts multipart form data (corpus files + multimodal references) to
// /api/companion/generate/upload, renders pipeline stage progress, and
// offers one-click import of the generated package as a live avatar.

(() => {
  'use strict';

  const API = '/api/companion';

  const $ = (id) => document.getElementById(id);

  const STAGE_KEYS = [
    'ingest',
    'analyze_corpus',
    'extract_persona',
    'configure_avatar',
    'configure_voice',
    'init_memory',
    'package',
  ];

  let currentTaskId = null;
  let tr = (key, fallback) => fallback || key;

  function stages() {
    return STAGE_KEYS.map((key) => [
      key,
      tr(`wizard.stages.${key}`, key),
    ]);
  }

  // ---------------------------------------------------------------- helpers

  function setTaskState(kind, text) {
    const pill = $('task-state');
    if (!kind) {
      pill.hidden = true;
      return;
    }
    pill.hidden = false;
    pill.className = `pill ${kind}`;
    pill.textContent = text;
  }

  function renderStages(completed, currentStage, failed) {
    $('progress-empty').style.display = 'none';
    const list = $('stage-list');
    list.replaceChildren();
    for (const [key, label] of stages()) {
      const li = document.createElement('li');
      li.className = 'stage';
      if (completed.includes(key)) li.classList.add('done');
      else if (failed && key === currentStage) li.classList.add('failed');
      else if (key === currentStage) li.classList.add('running');
      const dot = document.createElement('span');
      dot.className = 'dot';
      const text = document.createElement('span');
      text.textContent = label;
      li.append(dot, text);
      list.append(li);
    }
  }

  function renderRunning() {
    setTaskState('busy', tr('wizard.generating', '生成中…'));
    const first = STAGE_KEYS[0];
    renderStages([], first, false);
    $('result').classList.remove('show');
    $('import-result').textContent = '';
    $('import-result').className = '';
    $('manifest-view').classList.remove('show');
    $('retry-btn').hidden = true;
  }

  async function fetchTaskDetail(taskId) {
    const res = await fetch(`${API}/generate/${encodeURIComponent(taskId)}`);
    if (!res.ok) return null;
    return res.json();
  }

  async function renderFinished(task) {
    currentTaskId = task.id;
    renderStages(task.stages_completed || [], task.current_stage, task.status === 'failed');
    const retryBtn = $('retry-btn');
    if (task.status === 'completed') {
      setTaskState('ok', tr('wizard.completed', '生成完成'));
      retryBtn.hidden = true;
    } else if (task.status === 'failed') {
      setTaskState('err', `${tr('wizard.failed', '失败')}：${task.error || '?'}`);
      retryBtn.hidden = !(task.retries_remaining > 0);
      $('result').classList.add('show');
      return;
    } else {
      retryBtn.hidden = true;
    }
    const detail = await fetchTaskDetail(task.id);
    const artifact = detail && detail.artifact;
    $('r-task').textContent = task.id;
    $('r-package').textContent = artifact ? artifact.package_path : '—';
    const llm = artifact && artifact.analysis_summary && artifact.analysis_summary.llm;
    $('r-llm').textContent = llm
      ? `${llm.provider}${llm.model ? ` / ${llm.model}` : ''}${llm.degraded ? '（已降级）' : ''}`
      : '—';
    $('result').classList.add('show');
  }

  function applyStaticI18n() {
    const title = document.querySelector('header h1 span');
    if (title && title.nextSibling) {
      document.querySelector('header h1').childNodes[1].textContent =
        ` ${tr('wizard.title', '伴侣生成向导')}`;
    }
    const subtitle = document.querySelector('header p');
    if (subtitle) subtitle.textContent = tr('wizard.subtitle', subtitle.textContent);
    $('submit-btn').textContent = tr('wizard.startGenerate', '开始生成');
    $('retry-btn').textContent = tr('wizard.retry', '重试生成');
    $('publish-btn').textContent = tr('workshop.publish', '发布到工坊');
  }

  // ------------------------------------------------------------ file inputs

  for (const trigger of document.querySelectorAll('.file-trigger')) {
    const input = $(trigger.dataset.for);
    trigger.addEventListener('click', () => input.click());
    input.addEventListener('change', () => {
      const count = trigger.querySelector('.count');
      count.textContent = input.files.length
        ? `${input.files.length} 个文件`
        : '未选择';
    });
  }

  // ----------------------------------------------------------------- submit

  $('gen-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitBtn = $('submit-btn');
    submitBtn.disabled = true;
    renderRunning();

    const form = new FormData();
    form.append('companion_name', $('name').value.trim());
    form.append('locale', $('locale').value);
    form.append('corpus_text', $('corpus').value);
    form.append('system_prompt', $('prompt').value);
    form.append('live2d_model_id', $('live2d-id').value.trim());
    form.append('live2d_package_path', $('live2d-path').value.trim());
    const fileFields = [
      ['corpus_files', 'file-corpus'],
      ['reference_images', 'file-images'],
      ['reference_audio', 'file-audio'],
      ['reference_video', 'file-video'],
    ];
    for (const [field, inputId] of fileFields) {
      for (const file of $(inputId).files) form.append(field, file);
    }

    try {
      const res = await fetch(`${API}/generate/upload`, { method: 'POST', body: form });
      const task = await res.json();
      if (!res.ok) {
        setTaskState('err', `提交失败：${task.detail || res.status}`);
        return;
      }
      await renderFinished(task);
    } catch (err) {
      setTaskState('err', `请求异常：${err.message || err}`);
    } finally {
      submitBtn.disabled = false;
    }
  });

  $('retry-btn').addEventListener('click', async () => {
    if (!currentTaskId) return;
    $('retry-btn').disabled = true;
    renderRunning();
    try {
      const res = await fetch(
        `${API}/generate/${encodeURIComponent(currentTaskId)}/retry`,
        { method: 'POST' },
      );
      const task = await res.json();
      if (!res.ok) {
        setTaskState('err', task.detail || String(res.status));
        return;
      }
      await renderFinished(task);
    } catch (err) {
      setTaskState('err', err.message || String(err));
    } finally {
      $('retry-btn').disabled = false;
    }
  });

  $('publish-btn').addEventListener('click', async () => {
    if (!currentTaskId) return;
    const out = $('import-result');
    out.className = '';
    out.textContent = '…';
    try {
      const res = await fetch(
        `${API}/workshop/publish/${encodeURIComponent(currentTaskId)}`,
        { method: 'POST' },
      );
      const body = await res.json();
      if (!res.ok) {
        out.className = 'err';
        out.textContent = body.detail || String(res.status);
        return;
      }
      out.className = 'ok';
      out.textContent = body.export_path || tr('workshop.publish', '已发布');
    } catch (err) {
      out.className = 'err';
      out.textContent = err.message || String(err);
    }
  });

  // ----------------------------------------------------------------- import

  $('import-btn').addEventListener('click', async () => {
    if (!currentTaskId) return;
    const out = $('import-result');
    out.className = '';
    out.textContent = '导入中…';
    try {
      const res = await fetch(
        `${API}/generate/${encodeURIComponent(currentTaskId)}/import`,
        { method: 'POST' },
      );
      const body = await res.json();
      if (!res.ok) {
        out.className = 'err';
        out.textContent = res.status === 422
          ? `无法导入：${body.detail}（提示：提供 Live2D 包路径后重新生成）`
          : `导入失败：${body.detail || res.status}`;
        return;
      }
      out.className = 'ok';
      const avatar = body.avatar || {};
      out.textContent =
        `已导入并激活：${avatar.display_name || avatar.id}（模型 slug：${avatar.slug}）`;
    } catch (err) {
      out.className = 'err';
      out.textContent = `导入异常：${err.message || err}`;
    }
  });

  // --------------------------------------------------------------- manifest

  $('manifest-btn').addEventListener('click', async () => {
    if (!currentTaskId) return;
    const view = $('manifest-view');
    if (view.classList.contains('show')) {
      view.classList.remove('show');
      return;
    }
    try {
      const res = await fetch(
        `${API}/generate/${encodeURIComponent(currentTaskId)}/manifest`,
      );
      const body = await res.json();
      view.textContent = JSON.stringify(body, null, 2);
    } catch (err) {
      view.textContent = `manifest 加载失败：${err.message || err}`;
    }
    view.classList.add('show');
  });

  window.companionI18n.load().then(({ t }) => {
    tr = t;
    applyStaticI18n();
  });
})();
