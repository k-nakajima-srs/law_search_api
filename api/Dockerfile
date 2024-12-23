# api/Dockerfile
FROM python:3.11

# 必要なライブラリをインストールするための作業ディレクトリを作成
WORKDIR /app

# requirements.txtをコピーし、依存関係をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションのソースコードをコピー
COPY . .

# Flaskアプリケーションを起動
CMD ["python", "app.py"]
