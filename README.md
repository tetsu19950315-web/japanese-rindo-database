# 日本林道データベース / Codex引き継ぎリポジトリ

## このリポジトリの目的

日本全国の未舗装林道情報を将来的に一元化するプロジェクト。ただし現在の最優先は、**2026年7月11〜12日の長野県での林道アタックに間に合う、仲間内で実際に使えるMVP**を作ること。

MVPは次を満たす。

- スマホで動く
- 仲間とURL共有できる
- 林道の場所を地図上で視覚的に見られる
- 林道をタップすると重要情報（カルテ）が見られる
- 林道入口までGoogle Mapsでナビ開始できる

## 最初に読む順番

1. `AGENTS.md` — Codexの最優先行動規範
2. `STATUS.md` — 現在地と既存データ
3. `TASKS.md` — 今すぐ進める順番
4. `docs/MVP_REQUIREMENTS.md` — MVPの受け入れ条件
5. `docs/RESEARCH_PROTOCOL.md` — Lv0収集ルール
6. `docs/DATA_MODEL.md` — データ構造
7. `docs/DECISIONS.md` — 決定事項と保留事項

## 既存データ

- `data/raw/NGN_Lv0_Master_高速モード_v0.1.csv`
  - 長野県Lv0高速モード
  - 104件
  - 列: `ID,林道名,取得元`
  - 行政資料主体
  - 完全版ではない
- `data/reference/林道マスター_v2.xlsx`
  - 将来の詳細マスター項目の参考資料
  - 現時点の唯一の正はLv0 CSVではなく、目的ごとに使い分ける

## Codexへの最初の依頼

`prompts/CODEX_BOOTSTRAP_PROMPT.md` をそのまま使う。

## 基本方針

**設計を広げるより、まず動くものを完成させる。**

全国対応、Supabase、Flutter、認証、投稿機能、オフライン地図は将来候補。今週末MVPでは実装しない。

## GitHub Pages公開

- ルート `index.html` を GitHub Pages 用の公開入口として使用する
- 見た目と挙動の本体は `app/` に置く
- 公開対象は `scripts/build_pages_bundle.py` で `tmp/pages-dist/` に束ねる
- GitHub Actions は `.github/workflows/deploy-pages.yml` で `main` への push 時に Pages へ配備する
