# NovelGameRDP

---

**Project Overview**
- **意図**: ノベルゲームをスマートフォンで快適に遊びたいという個人的な願望から生まれたプロジェクトです。
- **最適化対象**: 本プロジェクトはノベルゲーム（ビジュアルノベル）に特化しています。

**Features**
- **ビデオ配信**: サーバー上の画面をキャプチャしてクライアントに配信します。
- **音声経路**: サーバーから音声をキャプチャして WebRTC 経路で配信します。
- **トラックパッド**: クライアントのトラックパッドオーバーレイで相対移動・スクロール・左右クリックを送信します。

**Server Usage**
- **起動**: ワークスペースのルートから次のコマンドで起動します（Python がインストール済みであること）。

```bash
python src/server.py
```

- **設定**: サーバー設定は [src/config.json](src/config.json) にあります。必要に応じて `SERVER_IP`、`SCREEN_FPS`、`SCREEN_MONITOR_INDEX` などを編集してください。
- **ポート**: シグナリング用 WebSocket はデフォルトで `ws://<SERVER_IP>:8765` を使用します。ファイアウォールやルーターの設定に注意してください。

**Client Usage**
- **起動方法**: `test/client.html` は単体の静的ページです。ローカルで確認する場合は HTTP サーバーを立ててブラウザで開いてください。

- ブラウザで開く: [http://localhost:8000/test/client.html](http://localhost:8000/test/client.html)

- **操作**: クライアントのビデオ上に表示されるトラックパッド領域で相対移動を行い、2本指でスクロール、左右ボタンでクリック送信が可能です。

**Python 作業環境の準備**

- **開発環境**: Python 3.12 を推奨します。

- **推奨手順 (Windows PowerShell)**

```powershell
# 仮想環境作成
python -m venv .venv
# 有効化
.\\.venv\\Scripts\\Activate.ps1
# 依存インストール
pip install -r requirements.txt
```

- **推奨手順 (bash / WSL / macOS / Linux)**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

- **依存**: 依存パッケージは [requirements.txt](requirements.txt) を参照してください。音声や画面キャプチャはネイティブライブラリに依存するため、環境ごとの追加セットアップが必要な場合があります。


**主要ファイル**
- **サーバー本体**: [src/server.py](src/server.py)
- **クライアント（テスト）**: [test/client.html](test/client.html)
- **設定**: [src/config.json](src/config.json)
- **依存**: [requirements.txt](requirements.txt)

