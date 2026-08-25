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


# ---------- fact seed extraction (Phase 5 M4, opt-in stage) ----------
# %s placeholders: (companion_name, corpus_text)

COMPANION_FACT_SEED_PROMPT = {
    'zh': """你是一个记忆事实抽取专家。用户想为名为「%s」的虚拟伴侣建立长期记忆，下面是用户提供的语料：

======以下为语料======
%s
======以上为语料======

请从语料中抽取**高置信度的原子事实**，只返回如下 JSON（不要附加任何解释文本）：
{"facts": [{"entity": "master 或 neko 或 relationship", "content": "一句完整、独立成立的事实", "importance": 1到10的整数, "confidence": 0.0到1.0的小数}]}

要求：
1. 只抽取语料中**明确陈述**的事实，推测、演绎、氛围描写一律不要。
2. entity 含义：master=用户本人的事实，neko=该伴侣角色自身的事实，relationship=两者关系的事实。
3. confidence 为你对该事实真实成立的把握，仅对语料原文直接支持的事实给 0.8 以上。
4. 最多 10 条；语料中没有可靠事实时返回 {"facts": []}。""",

    'en': """You are a memory-fact extraction expert. The user wants to build long-term memory for a virtual companion named "%s". Below is the corpus the user provided:

======corpus begins======
%s
======corpus ends======

Extract **high-confidence atomic facts** from the corpus and return ONLY the following JSON (no extra prose):
{"facts": [{"entity": "master or neko or relationship", "content": "one complete, self-contained fact sentence", "importance": integer 1-10, "confidence": decimal 0.0-1.0}]}

Requirements:
1. Only extract facts that are **explicitly stated** in the corpus; no speculation, deduction or mood description.
2. entity meaning: master = a fact about the user, neko = a fact about the companion character itself, relationship = a fact about their relationship.
3. confidence is your certainty that the fact holds; only give 0.8+ to facts directly supported by the corpus text.
4. At most 10 facts; return {"facts": []} when the corpus has no reliable facts.""",

    'ja': """あなたは記憶事実抽出の専門家です。ユーザーは「%s」という名前のバーチャルコンパニオンの長期記憶を構築しようとしています。以下はユーザーが提供したコーパスです：

======コーパス開始======
%s
======コーパス終了======

コーパスから**高置信度の原子的事実**を抽出し、次の JSON のみを返してください（説明文は一切不要）：
{"facts": [{"entity": "master / neko / relationship のいずれか", "content": "単独で成立する完結した一文の事実", "importance": 1〜10の整数, "confidence": 0.0〜1.0の小数}]}

要件：
1. コーパスに**明示的に記述された**事実のみを抽出し、推測・演繹・雰囲気描写は含めないこと。
2. entity の意味：master=ユーザー本人の事実、neko=コンパニオンキャラ自身の事実、relationship=両者の関係の事実。
3. confidence はその事実が成立する確信度。コーパス原文が直接裏付ける事実にのみ 0.8 以上を与えること。
4. 最大 10 件。信頼できる事実がない場合は {"facts": []} を返すこと。""",

    'ko': """당신은 기억 사실 추출 전문가입니다. 사용자가 「%s」라는 이름의 가상 컴패니언을 위한 장기 기억을 구축하려고 합니다. 아래는 사용자가 제공한 코퍼스입니다:

======코퍼스 시작======
%s
======코퍼스 끝======

코퍼스에서 **높은 확신도의 원자적 사실**을 추출하고 다음 JSON만 반환하세요(설명 텍스트 금지):
{"facts": [{"entity": "master 또는 neko 또는 relationship", "content": "단독으로 성립하는 완결된 한 문장의 사실", "importance": 1~10의 정수, "confidence": 0.0~1.0의 소수}]}

요구 사항:
1. 코퍼스에 **명시적으로 서술된** 사실만 추출하고 추측, 연역, 분위기 묘사는 제외할 것.
2. entity 의미: master=사용자 본인에 대한 사실, neko=컴패니언 캐릭터 자신에 대한 사실, relationship=둘의 관계에 대한 사실.
3. confidence는 해당 사실이 성립한다는 확신도이며, 코퍼스 원문이 직접 뒷받침하는 사실에만 0.8 이상을 부여할 것.
4. 최대 10개. 신뢰할 수 있는 사실이 없으면 {"facts": []}를 반환할 것.""",

    'ru': """Вы — эксперт по извлечению фактов для памяти. Пользователь хочет построить долговременную память для виртуального компаньона по имени «%s». Ниже приведён корпус, предоставленный пользователем:

======начало корпуса======
%s
======конец корпуса======

Извлеките из корпуса **атомарные факты с высокой достоверностью** и верните ТОЛЬКО следующий JSON (без пояснений):
{"facts": [{"entity": "master, neko или relationship", "content": "одно законченное, самодостаточное предложение-факт", "importance": целое число 1-10, "confidence": десятичное число 0.0-1.0}]}

Требования:
1. Извлекайте только факты, **явно указанные** в корпусе; никаких домыслов, выводов или описаний атмосферы.
2. Значение entity: master = факт о пользователе, neko = факт о самом персонаже-компаньоне, relationship = факт об их отношениях.
3. confidence — ваша уверенность в истинности факта; давайте 0.8+ только фактам, прямо подтверждённым текстом корпуса.
4. Не более 10 фактов; верните {"facts": []}, если в корпусе нет надёжных фактов.""",
}


# ---------- persona refine (Phase 5 M4, correction tier) ----------
# %s placeholders: (companion_name, current_system_prompt, user_feedback)

COMPANION_PERSONA_REFINE_PROMPT = {
    'zh': """你是一个虚拟伴侣人设修订专家。名为「%s」的虚拟伴侣已有如下 system prompt：

======当前 system prompt======
%s
======当前 system prompt 结束======

用户对该人设提出了如下反馈：
%s

请基于反馈对 system prompt 做**最小必要修订**，只返回如下 JSON（不要附加任何解释文本）：
{"system_prompt": "修订后的完整 system prompt", "change_summary": "一两句话说明改了什么"}

要求：
1. 只修改与反馈直接相关的部分，未被反馈涉及的设定原样保留。
2. 保持原有的人称、篇幅量级和写作风格。
3. 反馈与既有设定冲突时以反馈为准。""",

    'en': """You are a virtual-companion persona editor. The companion named "%s" currently has this system prompt:

======current system prompt======
%s
======current system prompt ends======

The user gave the following feedback about the persona:
%s

Apply the **minimal necessary revision** to the system prompt based on the feedback, and return ONLY the following JSON (no extra prose):
{"system_prompt": "the complete revised system prompt", "change_summary": "one or two sentences describing what changed"}

Requirements:
1. Only change the parts directly addressed by the feedback; keep everything else verbatim.
2. Preserve the original person, length scale and writing style.
3. When the feedback conflicts with the existing settings, the feedback wins.""",

    'ja': """あなたはバーチャルコンパニオンのキャラ設定修訂の専門家です。「%s」という名前のコンパニオンには現在、次の system prompt があります：

======現在の system prompt======
%s
======現在の system prompt 終わり======

ユーザーはこのキャラ設定について次のフィードバックを出しました：
%s

フィードバックに基づき system prompt に**必要最小限の修訂**を行い、次の JSON のみを返してください（説明文は一切不要）：
{"system_prompt": "修訂後の完全な system prompt", "change_summary": "何を変えたかの一〜二文の説明"}

要件：
1. フィードバックに直接関わる部分のみを変更し、それ以外の設定はそのまま保持すること。
2. 元の人称・分量・文体を維持すること。
3. フィードバックが既存設定と矛盾する場合はフィードバックを優先すること。""",

    'ko': """당신은 가상 컴패니언 페르소나 수정 전문가입니다. 「%s」라는 이름의 컴패니언에는 현재 다음 system prompt가 있습니다:

======현재 system prompt======
%s
======현재 system prompt 끝======

사용자가 이 페르소나에 대해 다음 피드백을 제시했습니다:
%s

피드백에 근거해 system prompt에 **최소한의 필요한 수정**만 가하고 다음 JSON만 반환하세요(설명 텍스트 금지):
{"system_prompt": "수정된 완전한 system prompt", "change_summary": "무엇을 바꿨는지 한두 문장의 설명"}

요구 사항:
1. 피드백과 직접 관련된 부분만 수정하고 나머지 설정은 그대로 유지할 것.
2. 원래의 인칭, 분량, 문체를 유지할 것.
3. 피드백이 기존 설정과 충돌하면 피드백을 우선할 것.""",

    'ru': """Вы — редактор персон виртуальных компаньонов. У компаньона по имени «%s» сейчас такой system prompt:

======текущий system prompt======
%s
======конец текущего system prompt======

Пользователь дал следующий отзыв о персоне:
%s

Внесите в system prompt **минимально необходимые правки** на основе отзыва и верните ТОЛЬКО следующий JSON (без пояснений):
{"system_prompt": "полный исправленный system prompt", "change_summary": "одно-два предложения о том, что изменилось"}

Требования:
1. Меняйте только то, что прямо затронуто отзывом; всё остальное сохраните дословно.
2. Сохраните исходное лицо повествования, объём и стиль.
3. При конфликте отзыва с существующими настройками приоритет у отзыва.""",
}
