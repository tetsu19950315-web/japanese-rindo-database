# PLANS — 実行計画

このファイルは複数時間にまたがる作業の進捗管理に使う。

## 現在の実行計画: 今週末MVP

### Goal

2026年7月11〜12日の実走で、仲間がスマホから使える林道マップを完成させる。

### Milestones

- [x] M1: 茅野・諏訪候補CSV完成
- [x] M2: 10件以上の位置情報取得
- [x] M3: 実走候補3〜5本決定
- [x] M4: カルテ3〜5本完成
- [x] M5: 地図MVPがローカルで動く
- [ ] M6: 公開URLからスマホで動く
- [ ] M7: Google Mapsナビ遷移確認

### 2026-07-08 P0実行順

1. Lv0 CSVを現環境で検証する。
2. Lv0から茅野市・諏訪市周辺候補を10〜30件抽出し、`data/processed/suwa_chino_candidates.csv` を作る。
3. 10件以上に入口または代表点の位置情報と出典を付け、`data/processed/suwa_chino_locations.csv` と `data/processed/routes.geojson` を作る。
4. 最小カルテを `data/processed/karte.json` に作る。
5. `app/` に静的Leaflet地図を実装し、ローカルで表示確認する。

### Working notes

作業中に重要な発見、ブロッカー、変更理由を追記する。

- 2026-07-08: Windows作業環境では `python` がPATHにないため、Codex bundled Pythonを使って検証する。
- 2026-07-08: Lv0 CSVのファイル名が作業環境上で文字化けして表示される。ID・列・内容は既存データを保持し、当面は検証済みCSVとして扱う。
- 2026-07-08: `data/processed/suwa_chino_candidates.csv` を17件で作成。
- 2026-07-08: `data/processed/suwa_chino_locations.csv` に10件の位置データを作成。諏訪市7件は公式PDF概要図1/7の番号位置、茅野市3件はOSM代表点を使用。
- 2026-07-08: `app/` にLeaflet静的MVPを実装し、ローカルURL `http://127.0.0.1:8000/app/` で応答確認。
- 2026-07-08: 次はP0-3として、10件の地図表示候補から実走候補3〜5本を選定する。選定条件は、行動エリア適合、未舗装可能性の公開情報、入口アクセス現実性、情報量。
- 2026-07-08: 実走候補は4本に決定。`猿ヶ入 / 棚嵐線 / 赤ジッコ線 / 扇平南峠線`。予備は `付上線`。
- 2026-07-08: 次はP0-4として、上記4本の正式カルテを作る。通行情報・未舗装手がかり・入口終点・注意点は、出典付きで `data/processed/karte.json` に整理する。
- 2026-07-08: `data/processed/karte.json` を作成し、4本の正式カルテを整備。`app/` 側も同ファイルの内容を優先表示するよう更新。
- 2026-07-08: `app/` に本命/予備フィルタとURL共有状態を追加。公開後は、そのまま仲間へ個別候補URLを渡せる状態。
- 2026-07-08: GitHub Pages 公開用にルート `index.html`、`scripts/build_pages_bundle.py`、`.github/workflows/deploy-pages.yml` を追加。`tmp/pages-dist/` への束ねとローカル root 配信で読み込み確認済み。
- 2026-07-08: `git` 初期化は実施。GitHub 側公開はアカウント認証待ち。
- 2026-07-09: GitHub リポジトリ `tetsu19950315-web/japanese-rindo-database` を作成し、`main` を初回 push。
- 2026-07-09: `actions/deploy-pages` 方式は初回実行で「Pages 未有効」のため失敗。`gh-pages` ブランチへ静的成果物を直接公開する方式に切替。
- 2026-07-09: 公開URL `https://tetsu19950315-web.github.io/japanese-rindo-database/` は HTTP 200 応答を確認。`karte.json` と共有URL形式も応答確認済み。
- 2026-07-09: `.github/workflows/deploy-pages.yml` を `main` から `gh-pages` を自動更新する内容へ変更。次回 push で継続運用可能。

### Decision discipline

- 今週末に必要 → 実装
- 良いが不要 → `docs/DECISIONS.md` の保留へ
- 長期構想 → 記録のみ
