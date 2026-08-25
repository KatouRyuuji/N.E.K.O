# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Companion platform (companion/) tunables — generator LLM budgets & timeouts."""

COMPANION_CORPUS_MAX_TOKENS = 3000
"""Companion generator 语料分析阶段送入 LLM 的语料 token 上限。
- 用途：`companion/generator/pipeline.py` 的 analyze_corpus 阶段。用户语料
  （聊天记录 / 小说片段）可能非常长，HEAD+TAIL 截断保住开头的人设描述和
  结尾的近期语气。
- 取值：3000 —— 足够覆盖典型的人设卡 + 数十条聊天样本，同时保证单次分析
  调用不吃满 summary tier 的上下文窗口。"""

COMPANION_PROMPT_SEED_MAX_TOKENS = 800
"""Companion generator persona 阶段送入 LLM 的用户提示词种子 token 上限。
- 用途：`GenerationInput.system_prompt` 是用户自由输入，拼进 persona 抽取
  prompt 前先截断，防止超长粘贴撑爆输入。
- 取值：800 —— 一张完整角色卡的合理规模。"""

COMPANION_ANALYSIS_CONTEXT_MAX_TOKENS = 1200
"""Companion generator persona 阶段回灌的语料分析 JSON token 上限。
- 用途：analyze_corpus 阶段的结构化结果（traits / speaking_style / summary）
  序列化后拼进 persona prompt；LLM 输出理论上已被 output guard 限住，
  这里是防御性的二次上限。"""

COMPANION_GENERATOR_LLM_TIMEOUT_SECONDS = 90
"""Companion generator 单次 LLM 调用 timeout（秒）。
- 生成任务是后台批处理（用户在向导页等进度条），可以比对话路径宽松；
  但必须 < 上游转发服务器的 120s hard timeout（同
  MEMORY_LLM_HARD_TIMEOUT_SECONDS 的理由，留 margin 防止被转发层先截断）。"""

COMPANION_OLLAMA_DETECT_TIMEOUT_SECONDS = 2.0
"""本地 Ollama 探测（GET /api/tags）的 timeout（秒）。
- 探测目标是 loopback 端口，正常几毫秒返回；2s 足够覆盖冷启动的
  Ollama daemon，同时保证未安装 Ollama 时 pipeline 快速走 fallback。"""

COMPANION_UPLOAD_MAX_FILE_BYTES = 100 * 1024 * 1024
"""生成向导 multipart 上传单文件字节上限（100 MB）。
- 用途：`companion/generator/uploads.py`。参考视频/音频可能较大，但这是
  本地单用户应用，100 MB 足够覆盖典型的参考素材，同时防止误传超大文件
  写爆用户文档目录。超限文件整个上传请求以 413 拒绝。"""

COMPANION_UPLOAD_MAX_FILES_PER_FIELD = 20
"""生成向导单个多文件字段（语料/参考图/音频/视频）的文件数上限。
- 防御性上限：向导 UI 正常一次选几个文件，20 足够；超限以 413 拒绝，
  防止一次 multipart 请求塞入海量小文件。"""

COMPANION_FACT_SEED_MAX_SEEDS = 10
"""语料 → fact 种子阶段（Phase 5 M4，默认关）单次生成落入 manifest 的
fact 种子条数上限。
- 用途：`companion/generator/pipeline.py` 的 extract_fact_seeds 阶段。LLM
  输出的高置信事实按 confidence 过滤后再截到该上限，防止超长语料一次
  塞爆导入端的 fact 层。"""

COMPANION_FACT_SEED_MIN_CONFIDENCE = 0.8
"""fact 种子的最低置信度门槛（LLM 自报 0.0-1.0）。
- 低于该值的候选事实直接丢弃：fact 层是长期记忆的 ground truth，宁缺
  毋滥；语料里的推测/演绎内容应留在 persona 层由对话逐步验证。"""

COMPANION_REFINE_FEEDBACK_MAX_TOKENS = 800
"""人设迭代（POST /persona/{name}/refine）用户反馈的输入 token 上限。
- 用途：`companion/ai/refine.py` 拼 correction tier prompt 前截断用户
  自由输入的反馈文本，防止超长粘贴撑爆输入（与
  COMPANION_PROMPT_SEED_MAX_TOKENS 同理由、同量级）。"""

COMPANION_PERSONA_VERSION_MAX_SNAPSHOTS = 20
"""characters.json 卡片版本链（Phase 5 M4）单角色保留的快照数上限。
- 用途：`companion/ai/persona_versions.py`。每次 refine 写回 / 回滚前都
  快照上一版本，链长超限时丢最老的——20 个版本足够覆盖一轮完整的人设
  打磨，同时防止版本文件无限膨胀。"""

COMPANION_CORPUS_FILE_MERGE_MAX_CHARS = 200_000
"""上传语料文本文件合并进 `corpus_text` 的总字符上限。
- 用途：upload 端点把可解码的文本语料（.txt/.md/.json 等）拼接进
  `corpus_text` 供 analyze_corpus 阶段使用；LLM 侧另有
  COMPANION_CORPUS_MAX_TOKENS 的 token 截断，这里是磁盘→内存的一次
  粗粒度上限，防止超大语料文件占用内存。"""
