# 開発者ガイド

Project N.E.K.O. は avatar rendering、realtime/text interaction、persistent memory、Agent execution、plugin を備える open-source AI companion platform です。このサイトは current repository の contributor/integrator 向けで、pricing/provider marketing ではありません。

主な境界は `app/` services、`main_logic/` と `memory/`、`brain/`、Jinja/static + shared React chat、Vue plugin manager、N.E.K.O.-PC Electron shell、`docker/` です。

## 利用前に N.E.K.O. を確認する

| 質問 | ガイド |
| --- | --- |
| アプリは無料で、AI サービスにはどのような費用がかかるか | [料金と Provider](./cost-and-providers) |
| 完全にオフラインで動作するか | [ローカルとオフラインの境界](./local-and-offline) |
| 会話やメモリがどこへ送信される可能性があるか | [技術データフローとプライバシー制御](./data-and-privacy) |
| どの導入経路を選ぶべきか | [Steam、GitHub Releases、ソース](./install-options) |

## 開発を始める

| Goal | Page |
| --- | --- |
| Tools | [前提条件](./prerequisites) |
| Setup | [開発環境](./dev-setup) |
| First run | [クイックスタート](./quick-start) |
| Repository | [プロジェクト構造](./project-structure) |
| Services | [アーキテクチャ](/ja/architecture/) |
| Plugin | [Plugin Quick Start](/ja/plugins/quick-start) |
| Deploy | [デプロイ](/ja/deployment/) |

## Companion Platform

Companion Platform（`companion/` package、Phase 4 で統合済み）は corpus・prompt・reference media から import 可能な `.neko-companion` package を生成し、N.E.K.O. core 上で動かします。設計ドキュメントは repository 内 `docs/companion-platform/` にあります。

- **生成ウィザード** — `/static/companion/wizard/index.html`：multimodal upload（corpus / 画像 / 音声 / 動画 / Live2D package）、7 stage 進捗、ワンクリック「キャラクターとして import」。
- **ローカルモデルウィザード** — `/static/companion/ollama/index.html`：Ollama を probe し、モデル選択後 `POST /api/companion/ai/open-source/config` で routing を永続化。
- **Workshop ページ** — `/static/companion/workshop/index.html`：ローカル catalog のカード閲覧・プレビューと、完了した生成タスクの publish。
- **API** — すべて `/api/companion/*` prefix（末尾スラッシュなし）：`GET /api/companion/health`、生成（`POST /api/companion/generate`、`POST /api/companion/generate/upload`）、import（`POST /api/companion/import`）、avatar hot swap（`/api/companion/avatar/*`）、productivity（`/api/companion/productivity/*`）、metrics（`GET /api/companion/metrics`）、workshop（`GET /api/companion/workshop/catalog`、`GET /api/companion/workshop/entry/{catalog_id}`、`GET /api/companion/workshop/asset/{catalog_id}/{path}`、`POST /api/companion/workshop/publish/{task_id}`）、open-source AI（`GET /api/companion/ai/open-source`、`POST /api/companion/ai/open-source/config`）。
- **対話セッション** — `GET /api/companion/session/{character_name}` は text + realtime voice の集約セッション metadata（websocket routing、sanitized provider tier、protocol frame）を返します。`POST /api/companion/dialogue/session` は companion profile から両チャネルの connect info を生成します。
- **長時間生成** — 生成 endpoint は `?background=true` に対応（即時 `202`、`GET /api/companion/generate/{task_id}` を polling）。失敗タスクは `POST /api/companion/generate/{task_id}/retry` で失敗 stage から再開し、完了済み LLM stage は再実行されません。
- **ローカル open-source AI status** — `GET /api/companion/ai/open-source` はローカル Ollama daemon（`OLLAMA_HOST`、デフォルト `http://127.0.0.1:11434`）を probe し、可用性と解決済みの model / base-URL routing 設定を返します。クラウド key 未設定の場合、生成 pipeline は自動的にこの route へ fallback します（heuristics は最終手段）。
- **Corpus fact seeds（opt-in）** — 生成入力で `extract_fact_seeds: true` を指定すると、corpus から高信頼度の事実を抽出する LLM stage が追加され、package manifest に入ります。import 時に memory の fact 層へ `external_import` 由来として書き込まれます。LLM-only 設計：LLM 不達時は空リストを返し、事実の捏造はしません（生成タスクは失敗しません）。
- **Persona refine / versions** — `POST /api/companion/persona/{name}/refine` は既存キャラクターカードに correction tier の LLM を 1 round かけて diff 提案を返します（書き込みなし。tier 未設定は `503`）。`POST /api/companion/persona/{name}/refine/apply` は確認済み提案を、旧カードを version chain へ snapshot した上で永続化します。`GET /api/companion/persona/{name}/versions` で snapshot 一覧、`POST /api/companion/persona/{name}/rollback` で復元（現行カードも先に snapshot されるため rollback 自体も revert 可能）。
- **Sync protocol（read-only）** — `GET /api/companion/sync/manifest` はデバイス単位の snapshot（登録済み companion ごとに `.neko-companion` manifest + memory cursor）を返し、`GET /api/companion/sync/memory/{name}?since=...` は 2 台目のデスクトップインスタンス向け（モバイルは後続）に冪等・ページング対応の fact 層差分を提供します。desktop-authoritative。仕様は `docs/companion-platform/SYNC_PROTOCOL.md`。

Python examples はすべて `uv run`。同 revision の entrypoint/loader/workflow と異なる場合は current code を優先し、docs drift を報告してください。
