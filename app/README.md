# app

今週末MVPの静的Webアプリです。

## ローカル確認

リポジトリのルートで静的サーバーを立てて、次を開く:

- `http://127.0.0.1:8000/app/`

## 現在の読み込みデータ

- `data/processed/mvp_map_data.json`
- `data/processed/karte.json`
- `data/processed/ride_shortlist_2026-07-08.json`
- `data/processed/routes.geojson`

## MVPの現在地

- OSM / 国土地理院地図 / Googleマップの背景地図切替
- 長野県全域の候補代表点表示
- タップでカルテ表示
- Google Mapsナビ遷移
- 本命 / 予備 / 全件の切替
- URLで選択中の候補と表示状態を共有可能
- 現在地と入口までの直線距離表示
- 通行情報・注意事項を優先した現地判断カルテ
- 名前一致線形と周辺参考線形を区別したルート表示
- PWAホーム画面追加と基本オフライン対応
- 写真・位置付き現地記録の端末内保存とJSON書き出し

完全オフライン地図、ログイン、サーバー同期は対象外。

## 背景地図

- OSM: 初期表示。追加設定なしで利用可能
- 国土地理院地図: 「背景地図」から選択。標準地図タイルと出典表記を使用
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
