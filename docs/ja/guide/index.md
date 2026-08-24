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
- **Workshop ページ** — `/static/companion/workshop/index.html`：ローカルに publish 済みの `.neko-companion` catalog の閲覧と、完了した生成タスクの publish。
- **API** — すべて `/api/companion/*` prefix（末尾スラッシュなし）：`GET /api/companion/health`、生成（`POST /api/companion/generate`、`POST /api/companion/generate/upload`）、import（`POST /api/companion/import`）、avatar hot swap（`/api/companion/avatar/*`）、productivity（`/api/companion/productivity/*`）、workshop（`GET /api/companion/workshop/catalog`、`POST /api/companion/workshop/publish/{task_id}`）。
- **対話セッション** — `GET /api/companion/session/{character_name}` は text + realtime voice の集約セッション metadata（websocket routing、sanitized provider tier、protocol frame）を返します。`POST /api/companion/dialogue/session` は companion profile から両チャネルの connect info を生成します。
- **長時間生成** — 生成 endpoint は `?background=true` に対応（即時 `202`、`GET /api/companion/generate/{task_id}` を polling）。失敗タスクは `POST /api/companion/generate/{task_id}/retry` で失敗 stage から再開し、完了済み LLM stage は再実行されません。

Python examples はすべて `uv run`。同 revision の entrypoint/loader/workflow と異なる場合は current code を優先し、docs drift を報告してください。
