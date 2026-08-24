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
