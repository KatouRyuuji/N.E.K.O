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

"""
Companion generator prompt templates.

Used by ``companion/generator/pipeline.py`` for the corpus-analysis and
persona-extraction stages. Both prompts demand strict JSON output so the
pipeline can parse them with ``robust_json_loads`` and fall back to the
heuristic path on any malformed reply.
"""

from __future__ import annotations

from config.prompts.prompts_sys import _loc  # noqa: F401  (re-exported for callers)


# ---------- corpus analysis ----------
# %s placeholders: (companion_name, corpus_text)

COMPANION_CORPUS_ANALYSIS_PROMPT = {
    'zh': """你是一个角色设定分析专家。用户想创建一个名为「%s」的虚拟伴侣，下面是用户提供的语料（聊天记录、小说片段、人设描述等）：

======以下为语料======
%s
======以上为语料======

请分析语料并只返回如下 JSON（不要附加任何解释文本）：
{"detected_traits": ["性格特质关键词，2-6 个"], "speaking_style": "说话风格的一句话概括", "relationship_hints": ["语料中体现的人物关系线索，可为空"], "summary": "语料内容的两三句话摘要"}

要求：
1. detected_traits 用简短的中文关键词（如"温柔"、"活泼"、"傲娇"）。
2. speaking_style 描述语气、口癖、称呼习惯等。
3. 只依据语料内容，不要凭空编造。""",

    'en': """You are a character-profile analyst. The user wants to create a virtual companion named "%s". Below is the corpus the user provided (chat logs, novel excerpts, persona notes, etc.):

======corpus begins======
%s
======corpus ends======

Analyze the corpus and return ONLY the following JSON (no extra prose):
{"detected_traits": ["2-6 personality trait keywords"], "speaking_style": "one-sentence summary of the speaking style", "relationship_hints": ["relationship clues found in the corpus, may be empty"], "summary": "a two-to-three sentence summary of the corpus"}

Requirements:
1. detected_traits must be short keywords (e.g. "gentle", "cheerful", "tsundere").
2. speaking_style should cover tone, verbal tics, and forms of address.
3. Base everything strictly on the corpus; do not invent details.""",

    'ja': """あなたはキャラクター設定の分析専門家です。ユーザーは「%s」という名前のバーチャルコンパニオンを作成しようとしています。以下はユーザーが提供したコーパス（チャット履歴、小説の抜粋、キャラ設定メモなど）です：

======コーパス開始======
%s
======コーパス終了======

コーパスを分析し、次の JSON のみを返してください（説明文は一切不要）：
{"detected_traits": ["性格特徴のキーワード 2〜6 個"], "speaking_style": "話し方の一文要約", "relationship_hints": ["コーパスに現れた人間関係の手がかり（空でも可）"], "summary": "コーパス内容の 2〜3 文の要約"}

要件：
1. detected_traits は短いキーワード（例：「優しい」「元気」「ツンデレ」）。
2. speaking_style は口調・口癖・呼び方の習慣などを含めること。
3. コーパスの内容のみに基づき、勝手に創作しないこと。""",

    'ko': """당신은 캐릭터 설정 분석 전문가입니다. 사용자가 「%s」라는 이름의 가상 컴패니언을 만들려고 합니다. 아래는 사용자가 제공한 코퍼스(채팅 기록, 소설 발췌, 캐릭터 설정 메모 등)입니다:

======코퍼스 시작======
%s
======코퍼스 끝======

코퍼스를 분석하고 다음 JSON만 반환하세요(설명 텍스트 금지):
{"detected_traits": ["성격 특성 키워드 2~6개"], "speaking_style": "말투에 대한 한 문장 요약", "relationship_hints": ["코퍼스에 나타난 인물 관계 단서, 비어 있어도 됨"], "summary": "코퍼스 내용의 2~3문장 요약"}

요구 사항:
1. detected_traits는 짧은 키워드로 작성(예: "다정함", "발랄함", "츤데레").
2. speaking_style에는 어조, 말버릇, 호칭 습관 등을 포함할 것.
3. 코퍼스 내용에만 근거하고 임의로 지어내지 말 것.""",

    'ru': """Вы — эксперт по анализу персонажей. Пользователь хочет создать виртуального компаньона по имени «%s». Ниже приведён корпус, предоставленный пользователем (логи чатов, фрагменты романа, заметки о персонаже и т.д.):

======начало корпуса======
%s
======конец корпуса======

Проанализируйте корпус и верните ТОЛЬКО следующий JSON (без пояснений):
{"detected_traits": ["2-6 ключевых слов о чертах характера"], "speaking_style": "краткое описание манеры речи одним предложением", "relationship_hints": ["подсказки об отношениях из корпуса, может быть пустым"], "summary": "резюме корпуса в 2-3 предложениях"}

Требования:
1. detected_traits — короткие ключевые слова (например, «нежная», «весёлая», «цундэре»).
2. speaking_style должен охватывать тон, словесные привычки и формы обращения.
3. Опирайтесь строго на корпус, ничего не выдумывайте.""",
}


# ---------- persona extraction ----------
# %s placeholders: (companion_name, analysis_json, user_prompt_seed)

COMPANION_PERSONA_EXTRACT_PROMPT = {
    'zh': """你是一个虚拟伴侣人设撰写专家。请为名为「%s」的虚拟伴侣生成 system prompt 和初始记忆种子。

语料分析结果（JSON）：
%s

用户提供的提示词种子（可能为空，若非空必须尊重其设定）：
%s

只返回如下 JSON（不要附加任何解释文本）：
{"system_prompt": "第二人称写给角色的完整 system prompt，200-500 字，涵盖性格、说话风格、与主人的关系", "memory_seeds": [{"entity": "记忆主体标识（如 neko / relationship / preference）", "content": "一句完整的记忆内容"}]}

要求：
1. system_prompt 以「你是%s」开头。
2. memory_seeds 提供 2-5 条，内容具体、可长期使用。
3. 只依据分析结果和用户种子，不要编造冲突设定。""",

    'en': """You are a virtual-companion persona writer. Generate a system prompt and initial memory seeds for a companion named "%s".

Corpus analysis result (JSON):
%s

User-provided prompt seed (may be empty; if present its settings MUST be respected):
%s

Return ONLY the following JSON (no extra prose):
{"system_prompt": "a complete second-person system prompt for the character, covering personality, speaking style and the relationship with the user", "memory_seeds": [{"entity": "memory subject id (e.g. neko / relationship / preference)", "content": "one complete memory sentence"}]}

Requirements:
1. system_prompt must open with "You are %s".
2. Provide 2-5 memory_seeds with concrete, durable content.
3. Base everything on the analysis and the user seed; do not invent conflicting settings.""",

    'ja': """あなたはバーチャルコンパニオンのキャラ設定ライターです。「%s」という名前のコンパニオンのために system prompt と初期メモリーシードを生成してください。

コーパス分析結果（JSON）：
%s

ユーザー提供のプロンプトシード（空の場合あり。非空なら必ずその設定を尊重すること）：
%s

次の JSON のみを返してください（説明文は一切不要）：
{"system_prompt": "二人称でキャラクターに宛てた完全な system prompt。性格・話し方・ユーザーとの関係を含むこと", "memory_seeds": [{"entity": "記憶主体の識別子（例：neko / relationship / preference）", "content": "完結した一文の記憶内容"}]}

要件：
1. system_prompt は「あなたは%s」で始めること。
2. memory_seeds は 2〜5 件、具体的で長期利用に耐える内容にすること。
3. 分析結果とユーザーシードのみに基づき、矛盾する設定を創作しないこと。""",

    'ko': """당신은 가상 컴패니언 페르소나 작가입니다. 「%s」라는 이름의 컴패니언을 위한 system prompt와 초기 메모리 시드를 생성하세요.

코퍼스 분석 결과(JSON):
%s

사용자가 제공한 프롬프트 시드(비어 있을 수 있음, 비어 있지 않으면 반드시 그 설정을 존중할 것):
%s

다음 JSON만 반환하세요(설명 텍스트 금지):
{"system_prompt": "2인칭으로 캐릭터에게 쓰는 완전한 system prompt. 성격, 말투, 사용자와의 관계를 포함할 것", "memory_seeds": [{"entity": "기억 주체 식별자(예: neko / relationship / preference)", "content": "완결된 한 문장의 기억 내용"}]}

요구 사항:
1. system_prompt는 「당신은 %s」로 시작할 것.
2. memory_seeds는 2~5개, 구체적이고 장기적으로 쓸 수 있는 내용일 것.
3. 분석 결과와 사용자 시드에만 근거하고 상충하는 설정을 지어내지 말 것.""",

    'ru': """Вы — автор персон для виртуальных компаньонов. Создайте system prompt и начальные семена памяти для компаньона по имени «%s».

Результат анализа корпуса (JSON):
%s

Затравка от пользователя (может быть пустой; если она есть, её настройки ОБЯЗАТЕЛЬНЫ к соблюдению):
%s

Верните ТОЛЬКО следующий JSON (без пояснений):
{"system_prompt": "полный system prompt для персонажа во втором лице, охватывающий характер, манеру речи и отношения с пользователем", "memory_seeds": [{"entity": "идентификатор субъекта памяти (например, neko / relationship / preference)", "content": "одно законченное предложение-воспоминание"}]}

Требования:
1. system_prompt должен начинаться с «Ты — %s».
2. Предоставьте 2-5 memory_seeds с конкретным, долговечным содержанием.
3. Опирайтесь только на анализ и затравку пользователя; не выдумывайте противоречащих настроек.""",
}
