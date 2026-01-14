import tkinter as tk
from tkinter import messagebox
import json
import subprocess
import os
import socket

# 設定ファイルのパス
CONFIG_FILE = "src/config.json"

# デフォルト設定
default_settings = {
    "SCREEN_FPS": 30,
    "SCREEN_MONITOR_INDEX": 1,
    "AUDIO_SAMPLE_RATE": 48000,
    "AUDIO_CHANNELS": 1,
    "SERVER_IP": "192.168.128.125"
}

# サーバープロセス
server_process = None

# 設定を保存する関数
def save_settings():
    try:
        print(f"設定ファイルのパス: {CONFIG_FILE}")  # デバッグ用
        settings = {
            "SCREEN_FPS": int(screen_fps_entry.get()),
            "SCREEN_MONITOR_INDEX": int(screen_monitor_entry.get()),
            "AUDIO_SAMPLE_RATE": int(audio_sample_rate_entry.get()),
            "AUDIO_CHANNELS": int(audio_channels_entry.get()),
            "SERVER_IP": server_ip_entry.get()
        }
        with open(CONFIG_FILE, "w") as f:
            json.dump(settings, f, indent=4)
        print("設定が正常に保存されました")  # デバッグ用
        messagebox.showinfo("保存完了", "設定が保存されました！")
    except Exception as e:
        messagebox.showerror("エラー", f"設定の保存中にエラーが発生しました: {e}")
        print(f"エラー詳細: {e}")

# 設定を読み込む関数
def load_settings():
    try:
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return default_settings

# サーバーを起動する関数
def start_server():
    global server_process
    if server_process is None:
        try:
            server_path = os.path.join(os.path.dirname(__file__), "server.py")
            server_process = subprocess.Popen(["python", server_path], cwd=os.path.dirname(__file__))
            messagebox.showinfo("サーバー起動", "サーバーが起動しました！")
            server_status_label.config(text="サーバー状態: 起動中", fg="green")
        except Exception as e:
            messagebox.showerror("エラー", f"サーバーの起動に失敗しました: {e}")
    else:
        messagebox.showwarning("警告", "サーバーは既に起動しています！")

# サーバーを停止する関数
def stop_server():
    global server_process
    if server_process is not None:
        server_process.terminate()
        server_process = None
        messagebox.showinfo("サーバー停止", "サーバーを停止しました！")
        server_status_label.config(text="サーバー状態: 停止中", fg="red")
    else:
        messagebox.showwarning("警告", "サーバーは起動していません！")

# IPv4アドレスを取得する関数
def get_ipv4_address():
    try:
        hostname = socket.gethostname()
        ipv4_address = socket.gethostbyname(hostname)
        return ipv4_address
    except Exception as e:
        print(f"IPv4アドレスの取得中にエラーが発生しました: {e}")
        return None

# 現在の設定を読み込む
current_settings = load_settings()

# SERVER_IPを自動取得したIPアドレスに更新
ipv4_address = get_ipv4_address()
if ipv4_address:
    current_settings["SERVER_IP"] = ipv4_address

# GUIの構築
root = tk.Tk()
root.title("設定GUI")

# 各設定項目
tk.Label(root, text="キャプチャフレームレート (FPS):").grid(row=0, column=0, sticky="w")
screen_fps_entry = tk.Entry(root)
screen_fps_entry.insert(0, current_settings["SCREEN_FPS"])
screen_fps_entry.grid(row=0, column=1)

tk.Label(root, text="モニター番号:").grid(row=1, column=0, sticky="w")
screen_monitor_entry = tk.Entry(root)
screen_monitor_entry.insert(0, current_settings["SCREEN_MONITOR_INDEX"])
screen_monitor_entry.grid(row=1, column=1)

tk.Label(root, text="音声サンプルレート:").grid(row=2, column=0, sticky="w")
audio_sample_rate_entry = tk.Entry(root)
audio_sample_rate_entry.insert(0, current_settings["AUDIO_SAMPLE_RATE"])
audio_sample_rate_entry.grid(row=2, column=1)

tk.Label(root, text="音声チャンネル数:").grid(row=3, column=0, sticky="w")
audio_channels_entry = tk.Entry(root)
audio_channels_entry.insert(0, current_settings["AUDIO_CHANNELS"])
audio_channels_entry.grid(row=3, column=1)

tk.Label(root, text="サーバーIPアドレス:").grid(row=4, column=0, sticky="w")
server_ip_entry = tk.Entry(root)
server_ip_entry.insert(0, current_settings["SERVER_IP"])
server_ip_entry.grid(row=4, column=1)

# 保存ボタン
save_button = tk.Button(root, text="保存", command=save_settings)
save_button.grid(row=5, column=0, columnspan=2)

# サーバー起動・停止ボタン
start_button = tk.Button(root, text="サーバー起動", command=start_server)
start_button.grid(row=6, column=0)
stop_button = tk.Button(root, text="サーバー停止", command=stop_server)
stop_button.grid(row=6, column=1)

# サーバーの状態を表示するラベル
server_status_label = tk.Label(root, text="サーバー状態: 停止中", fg="red")
server_status_label.grid(row=7, column=0, columnspan=2)

# GUIの起動
root.mainloop()