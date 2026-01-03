import sounddevice as sd
import numpy as np
import wave

# 録音パラメータ
fs = 44100       # サンプルレート（Hz）
duration = 5     # 録音時間（秒）
channels = 1     # モノラル（ステレオの場合は2）

print(f"録音開始...({duration}秒間)")
# dtype を 'int16' に指定することで、16bit PCM データとして取得
recording = sd.rec(int(duration * fs), samplerate=fs, channels=channels, dtype='int16')
sd.wait()  # 録音終了まで待機
print("録音終了")

# 保存する WAV ファイルの名前
output_file = "output_device.wav"

# wave モジュールを使って WAV ファイルとして保存
with wave.open(output_file, 'wb') as wf:
    wf.setnchannels(channels)  # チャネル数
    wf.setsampwidth(2)         # 16bit → 2バイト
    wf.setframerate(fs)        # サンプルレート
    wf.writeframes(recording.tobytes())  # numpy 配列からバイト列に変換して書き込み

print(f"音声を {output_file} に保存しました。")