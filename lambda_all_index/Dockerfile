# lambda_register/Dockerfile
FROM public.ecr.aws/lambda/python:3.11

# 必要なライブラリをインストールするための作業ディレクトリを作成
WORKDIR /var/task

# requirements.txtをコピーし、依存関係をインストール
COPY requirements.txt .
#RUN pip install --no-cache-dir -r requirements.txt
RUN pip install -r requirements.txt

# Lambda関数のソースコードをコピー
COPY all_index.py ./

# Lambdaハンドラーを指定
# register.pyのlambda_handlerを指定
CMD ["all_index.lambda_handler"]
