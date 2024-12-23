# 法律データインデックス化サービス

法律XMLデータを解析し、MongoDBから取得したデータをOpenSearchにインデックス化するサービスです。このプログラムは、大量の法律データを効率的に処理し、高速検索を可能にするインフラストラクチャの構築を支援します。

## 概要
本プロジェクトでは以下の主な機能を提供します：
- MongoDBに保存されている法律データの取得
- OpenSearchとの接続とインデックス作成
- 法律XMLデータのパースと必要なデータの抽出
- OpenSearchへのバルクインサートによる効率的なデータ登録

## 機能

1. **法律データの取得**
   - MongoDBに保存された法律データ(`laws`コレクション)を指定された範囲で取得します。

2. **XML解析**
   - `ja_law_parser` ライブラリを使用して法律データ(XML)を解析し、必要な情報を抽出します。

3. **OpenSearchへのインデックス**
   - 抽出したデータをOpenSearchのインデックスに登録します。
   - インデックスが存在しない場合は作成されます。

4. **エラーハンドリング**
   - MongoDB、OpenSearch、XML解析で発生するエラーをキャッチし、ログに記録します。

## 環境変数

以下の環境変数を事前に設定する必要があります。

| 環境変数名       | 説明                                | デフォルト値        |
|-------------------|-------------------------------------|--------------------|
| `OPENSEARCH_ENDPOINT` | OpenSearchエンドポイント         | `127.0.0.1`       |
| `INDEX_NAME`          | OpenSearchインデックス名         | `law-index`       |
| `OPENSEARCH_USER`     | OpenSearchユーザー名             | `admin`           |
| `OPENSEARCH_PASS`     | OpenSearchパスワード             | `SunrisePass123!` |
| `DOCDB_URI`           | MongoDB接続URI                  | `mongodb://root:example@localhost:27017` |

## 主な依存ライブラリ

以下のPythonライブラリが必要です：
- `pymongo` - MongoDBとの接続と操作
- `opensearch-py` - OpenSearchとの接続とデータインデックス化
- `ja_law_parser` - 法律XMLデータの解析

ライブラリのインストール:
```bash
pip install pymongo opensearch-py ja-law-parser
```

## 使用方法

1. 必要な環境変数を設定します。
2. スクリプトをLambda関数としてデプロイする、またはPython環境で直接実行します。

### Lambda関数としての実行
AWS Lambdaで実行する場合、エントリーポイントとして `lambda_handler` 関数を使用します。この関数は以下の引数を受け取ります：
- `event`: 入力パラメータを含む辞書
  - `skip`: データ取得のスキップ数 (オプション、デフォルト: `0`)
  - `limit`: データ取得数 (オプション、デフォルト: `100`)
- `context`: 実行コンテキスト (使用されません)

### ローカル環境での実行
ローカル環境では `lambda_handler` に適切なイベントを渡すことで動作を確認できます。

例:
```python
event = {
    "body": json.dumps({
        "skip": 0,
        "limit": 100
    })
}
result = lambda_handler(event, None)
print(result)
```

## データ構造

### MongoDBのデータサンプル
```json
{
  "law_id": "123456",
  "xml_content": "<Law>...</Law>"
}
```

### OpenSearchのインデックスマッピング
`INDEX_NAME` に以下のマッピングが設定されます：
```json
{
  "properties": {
    "law_id": {"type": "keyword"},
    "law_num": {"type": "keyword"},
    "law_title": {"type": "text"},
    "enact_statement": {"type": "text"},
    "main_provision": {"type": "text"}
  }
}
```

## サービスフロー

1. **MongoDB 接続**
   - `DOCDB_URI` を使用してMongoDBに接続。
2. **OpenSearch 接続**
   - `OPENSEARCH_ENDPOINT` を使用してOpenSearchに接続。
3. **データ取得と解析**
   - 指定された範囲のデータを取得し、XMLを解析。
4. **インデックス作成**
   - インデックスが存在しない場合に初期化。
   - データを適切なフォーマットでインデックス化。

## エラーハンドリング

- すべての主要プロセス (MongoDB接続、OpenSearch接続、XML解析) において例外がキャッチされ、ログに記録されます。
- ログには Python のトレースバック情報も含まれます。

## ソースコードの構成

| ファイル名  | 概要                              |
|-------------|-----------------------------------|
| `index.py`  | メインスクリプト。全プロセスを管理 |

## 開発者向け情報

### 拡張可能性
- 新しいデータソースを追加 → `lambda_handler` にデータ取得処理を追加してください。
- スキーマ変更 → OpenSearchのマッピングを `create_index_if_not_exists` 関数で調整してください。

以上です。質問や提案があれば気軽にお問い合わせください！