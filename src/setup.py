# setup.py
# python src/setup.py py2exe で実行

from setuptools import setup
import py2exe
 
# 実行可能ファイルに変換するスクリプトを指定
setup(
    windows=['src/gui.py'],  # GUIアプリケーションとして指定
    py_modules=['gui', 'server'],  # 明示的にモジュールを指定
    options={
        'py2exe': {
            'includes': [],  # 必要なモジュールを指定
            'excludes': [],  # 除外するモジュールを指定
            'compressed': True  # 圧縮を有効化
        }
    },
    data_files=[('', ['src/config.json'])],  # config.jsonを含める
    zipfile=None  # zipファイルを作成しない
)