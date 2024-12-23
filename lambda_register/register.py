import os
import json
from pymongo import MongoClient, UpdateOne
from pymongo.errors import ConnectionFailure

# DocumentDBの接続情報
DOCDB_URI = os.environ.get('DOCDB_URI')

if DOCDB_URI is None:
    raise ValueError("DOCDB_URIが設定されていません")

client = MongoClient(DOCDB_URI)
try:
    client.admin.command('ping')
    print("MongoDBに接続成功")
except ConnectionFailure:
    print("MongoDBに接続できません")
    raise

db = client['law_db']
collection = db['laws']

# バッチサイズの設定
BATCH_SIZE = 100  # 1回のバッチで処理するファイルの数


def lambda_handler(event, context):
    """
    Lambda関数のエントリーポイント。

    :param event: イベントデータを含む辞書。この辞書には、処理するデータのディレクトリを指定する 'data_dir' キーが含まれています。
    :param context: Lambda関数のランタイム情報。
    :return: HTTPステータスコードと、データがDocumentDBに正常に保存されたか、データディレクトリが提供されていないことを示すメッセージを含む辞書。
    """
    data_dir = event.get('data_dir')

    if data_dir:
        process_in_batches(data_dir)
        return {
            'statusCode': 200,
            'body': json.dumps('データをDocumentDBに保存しました')
        }

    return {
        'statusCode': 400,
        'body': json.dumps('データディレクトリが提供されていません')
    }


def process_in_batches(data_dir):
    """
    バッチ処理でXMLファイルを読み取り、DocumentDBに書き込みます。

    :param data_dir: XMLファイルが配置されているディレクトリのパス。
    :return: None
    """
    try:
        bulk_operations = []
        file_count = 0

        for root, _, files in os.walk(data_dir):
            for file in files:
                if file.endswith('.xml'):
                    try:
                        xml_file_path = os.path.join(root, file)
                        with open(xml_file_path, 'r', encoding='utf-8') as xml_file:
                            xml_data = xml_file.read()
                            law_id = file[:-4]  # ".xml"を取り除いて法令IDを取得
                            document = {
                                'law_id': law_id,
                                'xml_content': xml_data
                            }
                            # アップデート操作 (既存なら更新、存在しないなら新規作成)
                            bulk_operations.append(UpdateOne(
                                {'law_id': law_id},
                                {'$set': document},
                                upsert=True
                            ))
                            file_count += 1
                            if file_count % BATCH_SIZE == 0:
                                # バッチを別途書き込み処理
                                write_to_db(bulk_operations)
                                bulk_operations = []

                    except Exception as e:
                        print(f"{file} のファイル処理エラー: {e}")

        # バッチが残っている場合、最後に書き込み
        if bulk_operations:
            write_to_db(bulk_operations)

    except Exception as e:
        print(f"ディレクトリ処理エラー: {e}")


def write_to_db(bulk_operations):
    """
    データベースに対してバルク書き込み操作を実行します。

    :param bulk_operations: データベース上で実行するバルク書き込み操作のリスト。
    :return: None
    """
    try:
        if bulk_operations:
            result = collection.bulk_write(bulk_operations)
            print(f"新規作成またはアップデートされたドキュメントの数: {result.upserted_count + result.modified_count}")
    except Exception as db_e:
        print(f"データベースバルク挿入エラー: {db_e}")
