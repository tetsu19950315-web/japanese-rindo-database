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

### 複数入口

正規の林道IDは林道本体に対して1つとし、入口は `entrances` 配列で管理する。

```json
{
  "id": "NGN-000026",
  "name": "古城線",
  "displayLat": 35.733,
  "displayLon": 137.883,
  "entranceClassification": "through-two-accesses",
  "entrances": [
    {
      "id": "E1",
      "lat": 35.7315984,
      "lon": 137.8883453,
      "status": "estimated",
      "pointType": "approach",
      "accessClass": "public-road",
      "surface": "unknown",
      "navEnabled": true,
      "source": "OpenStreetMapの路線端点と接続道路",
      "checkedOn": "2026-07-15"
    }
  ]
}
```

- 同一林道の入口は `E1`、`E2` で区別し、林道ID自体は変更しない。
- 地図上の内部キーは `NGN-000026:E1` の形式とする。
- `status` は `verified` / `estimated` を使用する。
- `pointType=approach` はGoogle Mapsが到達しやすい公道側の分岐直前を示す。
- 入口不明時は `entrances: []` とし、代表点を入口へ自動転記しない。
- Street View URLは座標から実行時に生成し、画像は保存しない。

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
