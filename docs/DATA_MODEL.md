# DATA_MODEL — データ構造

## 1. 現在の正規フォーマット: Lv0

```csv
ID,林道名,取得元
```

### ID

安定識別子。変更しない。

### 林道名

正式名称を優先。資料表記を保持する。

### 取得元

存在確認の根拠。資料名とURLを残す。

## 2. MVP位置データ（追加ファイル推奨）

Lv0本体を壊さず、別ファイルで管理する。

推奨:

`data/processed/suwa_chino_locations.csv`

列:

```csv
ID,表示緯度,表示経度,入口緯度,入口経度,出口緯度,出口経度,位置取得元,位置確認日
```

## 3. MVPカルテ（別ファイル推奨）

`data/processed/karte.json`

最小項目:

- id
- name
- summary
- surface_summary
- access_status
- cautions
- last_checked
- confidence
- sources

## 4. 地図データ

`data/processed/routes.geojson`

当初はPointでもよい。

LineStringが取得できた林道だけ線表示へ成長させる。

## 5. 将来の詳細マスター

`data/reference/林道マスター_v2.xlsx` を参考にする。

主な候補項目:

- ステータス
- 自治体
- 林道タイプ
- 入口/出口
- 総延長
- 未舗装距離/率
- 路面
- 難易度
- 推奨車種
- 完抜可否
- 通行状況
- 冬季閉鎖
- 景観
- ベストシーズン
- 最終確認日
- 最終実走者
- 情報信頼度
- GPX
- AI要約

今週末MVPでは詳細マスターを完全実装しない。
