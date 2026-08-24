// N.E.K.O. Companion Generation Wizard
// Posts multipart form data (corpus files + multimodal references) to
// /api/companion/generate/upload, renders pipeline stage progress, and
// offers one-click import of the generated package as a live avatar.

(() => {
  'use strict';

  const API = '/api/companion';

  const $ = (id) => document.getElementById(id);

  const STAGES = [
    ['ingest', '语料接收'],
    ['analyze_corpus', '语料分析'],
    ['extract_persona', '人设提取'],
    ['configure_avatar', '形象配置'],
    ['configure_voice', '声线配置'],
    ['init_memory', '记忆初始化'],
    ['package', '打包'],
  ];

  let currentTaskId = null;

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
    for (const [key, label] of STAGES) {
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
    setTaskState('busy', '生成中…');
    renderStages([], STAGES[0][0], false);
    $('result').classList.remove('show');
    $('import-result').textContent = '';
    $('import-result').className = '';
    $('manifest-view').classList.remove('show');
  }

  async function fetchTaskDetail(taskId) {
    const res = await fetch(`${API}/generate/${encodeURIComponent(taskId)}`);
    if (!res.ok) return null;
    return res.json();
  }

  async function renderFinished(task) {
    currentTaskId = task.id;
    renderStages(task.stages_completed || [], task.current_stage, task.status === 'failed');
    if (task.status === 'completed') {
      setTaskState('ok', '生成完成');
    } else {
      setTaskState('err', `失败：${task.error || '未知错误'}`);
      return;
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
})();
