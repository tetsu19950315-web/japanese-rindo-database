# app

今週末MVPの静的Webアプリです。

## ローカル確認

リポジトリのルートで静的サーバーを立てて、次を開く:

- `http://127.0.0.1:8000/app/`

## 現在の読み込みデータ

- `data/processed/nagano_map_data.json`
- `data/processed/karte.json`
- `data/processed/nagano_shortlist.json`
- `data/processed/nagano_routes.geojson`

## MVPの現在地

- OSM / OpenFreeMap / 地理院淡色 / 地理院航空写真 / Googleマップの背景地図切替
- 長野県全域の入口・代表点表示
- 同一林道IDに複数入口を持つ完抜け林道の①／②表示
- 入口不明候補の代表点表示とナビ無効化
- タップでカルテ表示
- Google Mapsナビ遷移
- APIキー不要のStreet View入口確認リンク
- 本命 / 予備 / 全件の切替
- URLで選択中の候補と表示状態を共有可能
- `road=NGN-000026&entry=E2` 形式で入口別に共有可能
- 現在地と入口までの直線距離表示
- 通行情報・注意事項を優先した現地判断カルテ
- 名前一致線形と周辺参考線形を区別したルート表示
- PWAホーム画面追加と基本オフライン対応
- 写真・位置付き現地記録の端末内保存とJSON書き出し

完全オフライン地図、ログイン、サーバー同期は対象外。

## 背景地図

- OSM: 初期表示。追加設定なしで利用可能
- OpenFreeMap: LibertyスタイルをMapLibreで表示。APIキー不要
- 地理院淡色: 「背景地図」から選択。候補点と路線を見やすく表示
- 地理院航空写真: 全国最新写真（シームレス）を表示
- Googleマップ: Google Maps JavaScript API の公式実装。APIキー設定後に利用可能

Googleマップを有効にする場合は、Google Cloud で Maps JavaScript API と課金を有効にし、`app/index.html` の設定へキーを追加する。

```html
googleMapsApiKey: "YOUR_GOOGLE_MAPS_API_KEY",
```

ブラウザから利用するキーはHTML上で参照できるため、Google Cloud側で HTTP リファラー制限を必ず設定する。公開版の許可例:

```text
https://tetsu19950315-web.github.io/japanese-rindo-database/*
```

APIキーが未設定または読み込みに失敗した場合は、現在のLeaflet地図を維持して案内を表示する。非公式なGoogleタイルURLは使用しない。
