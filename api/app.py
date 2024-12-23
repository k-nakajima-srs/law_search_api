import logging
import json
import traceback

from flask import Flask, jsonify, request
import requests
import os
from ja_law_parser.parser import LawParser
from ja_law_parser.model import Law
from pymongo import MongoClient
from opensearchpy import OpenSearch, RequestsHttpConnection

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)

LAMBDA_URL_REGISTER = "http://api_gateway:8080/register"  # Lambda関数のURL
LAMBDA_URL_INDEX = "http://api_gateway:8080/index"  # Lambda関数
DOCDB_URI = os.getenv('DOCDB_URI', 'mongodb://root:example@localhost:27017')
client = MongoClient(DOCDB_URI)
db = client['law_db']
collection = db['laws']

# OpenSearchの接続情報
OPENSEARCH_ENDPOINT = os.getenv('OPENSEARCH_ENDPOINT', '127.0.0.1')
INDEX_NAME = os.getenv('INDEX_NAME', 'law-index')
OPENSEARCH_USER = os.getenv('OPENSEARCH_USER', 'admin')
OPENSEARCH_PASS = os.getenv('OPENSEARCH_PASS', 'SunrisePass123!')

# OpenSearchクライアントの設定
client = OpenSearch(
    hosts=[{'host': OPENSEARCH_ENDPOINT, 'port': 9200}],
    http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),  # 必要であれば認証情報を指定
    use_ssl=False,
    verify_certs=False,
    connection_class=RequestsHttpConnection
)


@app.route('/register', methods=['POST'])
def add():
    """
    `POST /register` エンドポイントを処理します。この関数は、リクエストのJSONペイロードから `data_dir` を抽出し、それを事前定義されたLambda関数のURLに送信します。Lambda関数のレスポンスに応じて、関連情報をログに記録し、クライアントに適切なJSONレスポンスを返します。

    :return:
        - `data_dir` が提供されており、Lambda関数が正常に応答した場合は200 OKとLambda関数のJSONレスポンス。
        - JSON解析エラーが発生した場合は500 Internal Server Error。
        - リクエストのJSONペイロードに `data_dir` が含まれていない場合は400 Bad Request。
        - Lambda関数から受信したその他のHTTPステータスと対応するエラー詳細。
    """
    data_dir = request.json.get('data_dir')
    if data_dir:
        logging.info(f"Request sent to Lambda URL_REGISTER with data_dir: {data_dir}")
        response = requests.post(LAMBDA_URL_REGISTER, json={'data_dir': data_dir})

        logging.info(f"Response status code: {response.status_code}")
        logging.info(f"Response text: {response.text}")

        if response.status_code != 200:
            logging.error(f"Error Response from Lambda: {response.status_code} {response.text}")
            return jsonify({"error": "Lambda エラー", "details": response.text}), response.status_code

        try:
            response_json = response.json()
            return jsonify(response_json), response.status_code
        except json.decoder.JSONDecodeError as e:
            logging.error(f"JSONDecodeError: {e}")
            return jsonify({"error": "無効なJSONレスポンス", "details": response.text}), 500

    return jsonify({"error": "データディレクトリが提供されていません"}), 400


@app.route('/index', methods=['POST'])
def index():
    """
    `POST /index` エンドポイントを処理します。この関数は以下の操作を行います：

    1. パラメータなしでLambda URL_INDEXにリクエストの開始をログに記録します。
    2. 指定されたコレクションの総ドキュメント数を取得します。
    3. バッチサイズ10でドキュメントを処理し、LAMBDA_URL_INDEXのLambda関数を呼び出します。
    4. Lambda関数からのレスポンスのステータスコードとレスポンステキストをログに記録します。
    5. ステータスコードがエラーを示す場合、エラーをログに記録し、エラーの詳細を含むJSONレスポンスを返します。
    6. レスポンスをJSONとしてデコードしようとし、成功した場合、適切なステータスコードで返します。
    7. JSONデコードが失敗した場合、エラーをログに記録し、無効なJSONレスポンスを示すJSONレスポンスを返します。

    :return: Lambda関数からの結果またはエラーメッセージを含むJSONレスポンスと対応するHTTPステータスコード。
    """
    logging.info("Request sent to Lambda URL_INDEX without parameters")
    # 総ドキュメント数を取得
    total_docs = collection.count_documents({})
    batch_size = 10
    for skip in range(0, total_docs, batch_size):
        invoke_payload = {
            'skip': skip,
            'limit': batch_size
        }
        response = requests.post(LAMBDA_URL_INDEX, json=invoke_payload)

    logging.info(f"Response status code: {response.status_code}")
    logging.info(f"Response text: {response.text}")

    if response.status_code != 200:
        logging.error(f"Error Response from Lambda: {response.status_code} {response.text}")
        return jsonify({"error": "Lambda エラー", "details": response.text}), response.status_code

    try:
        response_json = response.json()
        return jsonify(response_json), response.status_code
    except json.decoder.JSONDecodeError as e:
        logging.error(f"JSONDecodeError: {e}")
        return jsonify({"error": "無効なJSONレスポンス", "details": response.text}), 500


@app.route('/search/by-id', methods=['GET'])
def search_by_id():
    """
    GETリクエストにより法律IDで文書を検索します。

    提供された法律IDクエリパラメータを使用して、ドキュメントデータベースから文書を取得します。
    文書が見つかった場合、それを200ステータスコードで返します。
    文書が見つからなかった場合、エラーメッセージとともに404ステータスコードを返します。
    法律IDが提供されていない場合、エラーメッセージとともに400ステータスコードを返します。

    :return: 文書またはエラーメッセージを含むJSONレスポンスと対応するHTTPステータスコード。
    """
    law_id = request.args.get('law_id')
    if law_id:
        document = fetch_from_documentdb_by_id(law_id)
        if document:
            return jsonify(document), 200
        else:
            return jsonify({"error": "ドキュメントが見つかりません"}), 404
    return jsonify({"error": "law_idが提供されていません"}), 400


@app.route('/search/by-query', methods=['GET'])
def search_by_query():
    """
    クエリに基づいてアイテムを検索するGETリクエストを処理します。

    リクエストの引数からクエリパラメータを抽出し、 `search_opensearch` 関数を使用して検索を実行します。クエリパラメータが提供されていない場合、エラーメッセージを返します。

    :return: 検索結果またはエラーメッセージを含むJSONレスポンスと対応するHTTPステータスコード。
    """
    query = request.args.get('query')
    if query:
        search_results = search_opensearch(query)
        return jsonify(search_results), 200
    return jsonify({"error": "クエリが提供されていません"}), 400


def search_opensearch(query):
    """
    OpenSearchを使用してクエリを実行します。

    :param query: OpenSearchデータベースをクエリするための検索クエリ文字列。
    :return: フォーマットされた検索結果を含む辞書のリスト。各辞書には `law_id`, `law_num`, `law_title` キーとそれに対応する値が含まれます。
    """
    logging.info("search start")
    # OpenSearchでmulti_matchクエリを使用して複数フィールドで検索
    search_query = {
        "_source": ["law_id", "law_num", "law_title"],  # 取得したいフィールドを指定
        "query": {
            "multi_match": {
                "query": query,
                "fields": ["law_title^3", "enact_statement", "main_provision"]
            }
        }
    }
    logging.info(f"search_query = {search_query}")

    # OpenSearchにクエリを送信
    response = client.search(index=INDEX_NAME, body=search_query)
    logging.info(f"search_response = {response}")

    # 結果の取得と処理
    if response:
        # 必要なフィールドだけを抽出してリフフォーマット
        results = [
            {
                "law_id": result["_source"].get("law_id"),
                "law_num": result["_source"].get("law_num"),
                "law_title": result["_source"].get("law_title")
            }
            for result in response["hits"]["hits"]
        ]
        return results
    else:
        return []


def fetch_from_documentdb_by_id(law_id):
    """
    law_idに基づいてドキュメントデータベースから文書を取得します。

    :param law_id: データベースから取得する法的文書の識別子。
    :return: `law_id` に対応する文書が見つかった場合、文書を返します。それ以外の場合はNoneを返します。文書の `_id` フィールドはObjectIdから文字列に変換されます。
    """
    document = collection.find_one({'law_id': law_id})
    if document:
        document['_id'] = str(document['_id'])  # ObjectId を文字列に変換
    return document

def parse_law_xml(parser, xml_string):
    """
    法律のXML文字列を解析します。

    :param parser: 提供されたXML文字列を解析するパーサオブジェクト。
    :type parser: object
    :param xml_string: 解析する必要があるXMLコンテンツ（文字列形式）。
    :type xml_string: str
    :return: パーサの解析メソッドの結果、または例外が発生した場合はNoneを返します。
    :rtype: objectまたはNone
    """
    try:
        if isinstance(xml_string, str):
            xml_string = xml_string.encode('utf-8')
        return parser.parse_from(xml_string)
    except Exception as e:
        print(f"parse_law_xml内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")
        return None

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
