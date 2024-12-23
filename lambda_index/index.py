import os
import json
import traceback
from pymongo import MongoClient
from ja_law_parser.parser import LawParser
from ja_law_parser.model import Law
from opensearchpy import OpenSearch, RequestsHttpConnection, helpers
from concurrent.futures import ThreadPoolExecutor, as_completed

# 環境変数から取得
OPENSEARCH_ENDPOINT = os.getenv('OPENSEARCH_ENDPOINT', '127.0.0.1')
INDEX_NAME = os.getenv('INDEX_NAME', 'law-index')
OPENSEARCH_USER = os.getenv('OPENSEARCH_USER', 'admin')
OPENSEARCH_PASS = os.getenv('OPENSEARCH_PASS', 'SunrisePass123!')
DOCDB_URI = os.getenv('DOCDB_URI', 'mongodb://root:example@localhost:27017')

# DocumentDBとOpenSearchの設定
try:
    print('MongoDBに接続中...')
    client = MongoClient(DOCDB_URI)
    db = client['law_db']
    collection = db['laws']
    print('MongoDBに接続しました。')

    print('OpenSearchに接続中...')
    clientOpenSearch = OpenSearch(
        hosts=[{'host': OPENSEARCH_ENDPOINT, 'port': 9200}],
        http_auth=(OPENSEARCH_USER, OPENSEARCH_PASS),
        use_ssl=False,
        verify_certs=False,
        connection_class=RequestsHttpConnection
    )
    print('OpenSearchに接続しました。')
except Exception as e:
    print(f"MongoDBまたはOpenSearch接続中のエラー: {str(e)}")
    print(f"トレースバック: {traceback.format_exc()}")


def lambda_handler(event, context):
    """
    Lambda関数のエントリーポイント。

    :param event: Lambda関数に対する入力イベント。この辞書には、'skip'および'limit'などのさまざまなパラメータが含まれることがあります。
    :param context: Lambda関数のランタイム情報を含むコンテキスト。このパラメータは関数ロジックでは使用されません。
    :return: statusCode と body を含む辞書。処理が成功した場合はステータスコード200が返され、失敗した場合はエラーメッセージとともにステータスコード500が返されます。
    """
    print(f"lambda_handler開始 - イベント: {event}")
    try:
        create_index_if_not_exists()

        parser = LawParser()

        if event and 'body' in event:
            print('イベントにボディがあります。')
            body = json.loads(event['body'])
        else:
            print('イベントにボディがないため、イベントを直接使用します（存在する場合）。')
            body = event if event else {}

        skip = int(body.get('skip', 0))
        limit = int(body.get('limit', 100))
        print(f'パラメータ: skip={skip}, limit={limit}')

        print('MongoDBからデータ取得中...')
        all_data = collection.find().skip(skip).limit(limit)

        if all_data is None:
            raise ValueError("MongoDBからデータが取得できませんでした")

        bulk_data = []

        def bulk_insert(bulk_data):
            try:
                if bulk_data:
                    helpers.bulk(clientOpenSearch, bulk_data)
            except Exception as e:
                print(f"バルクインサート中のエラー: {str(e)}")
                print(f"トレースバック: {traceback.format_exc()}")

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(process_law, parser, item) for item in all_data]
            for future in as_completed(futures):
                try:
                    index_data = future.result()
                    if index_data:
                        bulk_data.append(index_data)
                        if len(bulk_data) >= 10:
                            bulk_insert(bulk_data)
                            bulk_data = []
                except Exception as e:
                    print(f"アイテムの処理に失敗しました: {str(e)}")
                    print(f"トレースバック: {traceback.format_exc()}")
                    continue  # 次のアイテムに進む
        bulk_insert(bulk_data)

        return {
            'statusCode': 200,
            'body': json.dumps('処理が正常に完了しました')
        }
    except Exception as e:
        print(f"lambda_handler内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps(f"エラー: {str(e)}")
        }


def create_index_if_not_exists():
    """
    OpenSearchインデックスが存在しない場合に作成します。

    :return: None
    """
    try:
        print('インデックスの存在を確認中...')
        if not clientOpenSearch.indices.exists(INDEX_NAME):
            index_body = {
                "settings": {
                    "number_of_shards": 1,
                    "number_of_replicas": 1
                },
                "mappings": {
                    "properties": {
                        "law_id": {"type": "keyword"},
                        "law_num": {"type": "keyword"},
                        "law_title": {"type": "text"},
                        "enact_statement": {"type": "text"},
                        "main_provision": {"type": "text"}
                    }
                }
            }
            clientOpenSearch.indices.create(index=INDEX_NAME, body=index_body)
            print('インデックスが作成されました。')
        else:
            print('インデックスは既に存在します。')
    except Exception as e:
        print(f"create_index_if_not_exists内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")


def process_law(parser, item):
    """
    Law XMLコンテンツを解析し、インデックス用のデータを生成します。

    :param parser: 法律XMLコンテンツを解析するために使用するパーサのインスタンス。
    :param item: MongoDBから取得したアイテムの辞書。'law_id' と 'xml_content' を含む。
    :return: インデックス用にフォーマットされた法律データを含む辞書、またはエラー時にはNoneを返します。
    """
    try:
        if item is None:
            raise ValueError("MongoDBから取得したアイテムがNoneです")

        law_id = item.get('law_id')
        xml_content = item.get('xml_content')

        if law_id is None or xml_content is None:
            raise ValueError("アイテムにlaw_idまたはxml_contentが含まれていません")

        law = parse_law_xml(parser, xml_content)

        if not law or not hasattr(law, 'law_body'):
            raise ValueError("解析された法律にはlaw_bodyが含まれていません")

        print(law_id)

        law_obj = {
            "law_id": law_id,
            "law_num": law.law_num,
            "law_title": text_or_none(law.law_body.law_title),
            "enact_statement": text_or_none(law.law_body.enact_statement),
            "main_provision": texts_or_none(law.law_body.main_provision)
        }

        return {
            "_index": INDEX_NAME,
            "_id": law_id,
            "_source": law_obj
        }
    except Exception as e:
        print(f"process_law内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")
        return None


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


def text_or_none(obj):
    """
    オブジェクトの 'text' 属性を返します。

    :param obj: 'text' 属性を持つ可能性のある入力オブジェクト
    :return: オブジェクトの 'text' 属性（存在する場合）、存在しない場合はNone
    """
    try:
        if obj is None:
            return None
        return obj.text
    except Exception as e:
        print(f"text_or_none内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")
        return None


def texts_or_none(obj):
    """
    'texts' メソッドを持つオブジェクトのテキストを空白で結合して返します。

    :param obj: 'texts' メソッドを持つオブジェクト。
    :return: オブジェクトの 'texts' メソッドからのテキストを空白で結合した文字列、またはNone（オブジェクトがNoneまたはエラーが発生した場合）。
    """
    try:
        if obj is None:
            return None
        return " ".join(obj.texts())
    except Exception as e:
        print(f"texts_or_none内のエラー: {str(e)}")
        print(f"トレースバック: {traceback.format_exc()}")
        return None
