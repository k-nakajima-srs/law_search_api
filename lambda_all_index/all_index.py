import os
import json
import boto3
import requests
from pymongo import MongoClient
import concurrent.futures

# 環境変数から取得
LAMBDA_FUNCTION_NAME = os.getenv('LAMBDA_FUNCTION_NAME', 'lambda_index')
DOCDB_URI = os.getenv('DOCDB_URI', 'mongodb://root:example@localhost:27017')
IS_LOCAL = os.getenv('IS_LOCAL', 'false').lower() == 'true'
MAX_WORKERS = int(os.getenv('MAX_WORKERS', 5))  # MAX_WORKERSを整数に変換
batch_size = int(os.getenv('BATCH_SIZE', 100))  # 1回に処理するデータの量

# DocumentDBの設定
client = MongoClient(DOCDB_URI)
db = client['law_db']
collection = db['laws']

# Lambdaクライアント設定
if not IS_LOCAL:
    lambda_client = boto3.client('lambda')
else:
    lambda_base_url = f"http://{LAMBDA_FUNCTION_NAME}:8080"  # lambda_index Dockerコンテナのポートに接続


def async_post(url, payload):
    """
    指定されたURLに対してPOSTリクエストを非同期で送信します。

    :param url: POSTリクエストを送信するURL。
    :param payload: POSTリクエストに含めるペイロード（データ）。通常は辞書形式。
    :return: ステータスコードとレスポンステキストを含むタプル。
    """
    response = requests.post(url, data=json.dumps(payload))
    return response.status_code, response.text


def lambda_handler(event, context):
    """
    Lambda関数のエントリーポイント。DocumentDBのデータをバッチに分割し、Lambda関数を非同期に呼び出します。

    :param event: Lambda関数によって呼び出される際に渡されるイベントデータ。
    :param context: Lambda関数の実行環境に関するランタイム情報を含むオブジェクト。
    :return: ステータスコード200と成功メッセージを含むレスポンス辞書。
    """
    # 総ドキュメント数を取得
    total_docs = collection.count_documents({})

    # データをバッチに分割して非同期呼び出し
    future_executions = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:  # 並行呼び出しの最大数
        for skip in range(0, total_docs, batch_size):
            invoke_payload = {
                'skip': skip,
                'limit': batch_size
            }

            if not IS_LOCAL:
                response = lambda_client.invoke(
                    FunctionName=LAMBDA_FUNCTION_NAME,
                    InvocationType='Event',  # 非同期呼び出し
                    Payload=json.dumps(invoke_payload)
                )
                print(response)
            else:
                # future = executor.submit(async_post,
                #                          f"{lambda_base_url}/2015-03-31/functions/function/invocations",
                #                          invoke_payload)
                future = executor.submit(async_post,
                                         "http://api_gateway:8080/index",
                                         invoke_payload)
                future_executions.append(future)

        # 全てのスレッドの完了を待つ
        for future in concurrent.futures.as_completed(future_executions):
            status_code, text = future.result()
            print(status_code, text)

    return {
        'statusCode': 200,
        'body': json.dumps('Lambda function invoked successfully')  # Lambda関数が正常に呼び出されたことを示すメッセージ
    }
