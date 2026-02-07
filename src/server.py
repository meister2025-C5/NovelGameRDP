# 必要なパッケージ: aiortc, websockets, mss, opencv-python, av

import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, AudioStreamTrack
import cv2
import numpy as np
import mss
import sounddevice as sd
import threading
import wave
import os
import fractions



# 設定ファイルの絶対パスを取得
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

# デフォルト設定
default_settings = {
    "SCREEN_FPS": 30,
    "SCREEN_MONITOR_INDEX": 2,
    "AUDIO_SAMPLE_RATE": 48000,
    "AUDIO_CHANNELS": 1,
    "SERVER_IP": "192.168.128.125"
}

# 設定を読み込む関数
def load_settings():
    try:
        with open(CONFIG_FILE, "r") as f:
            settings = json.load(f)
            print("読み込んだ設定:", settings)  # デバッグ用出力
            return settings
    except FileNotFoundError:
        print("設定ファイルが見つかりません。デフォルト設定を使用します。")
        return default_settings

# 設定を読み込む
settings = load_settings()

# 画面キャプチャ設定
SCREEN_FPS = settings["SCREEN_FPS"]
SCREEN_MONITOR_INDEX = settings["SCREEN_MONITOR_INDEX"]

# 音声キャプチャ設定
AUDIO_SAMPLE_RATE = settings["AUDIO_SAMPLE_RATE"]
AUDIO_CHANNELS = settings["AUDIO_CHANNELS"]

# サーバーのIPアドレス設定
SERVER_IP = settings["SERVER_IP"]

class SystemAudioTrack(AudioStreamTrack):
	kind = "audio"

	def __init__(self, samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS, device_id=None):
		super().__init__()
		self.samplerate = samplerate
		self.channels = channels
		self.q = asyncio.Queue()
		self.loop = asyncio.get_event_loop()
		self.stream = None
		self.device_id = device_id
		self._pts = 0

	def start_recording(self):
		print("Starting audio recording...")
		blocksize = int(self.samplerate * 0.02)
		try:
			if self.device_id is not None:
				self.stream = sd.InputStream(
					device=self.device_id,
					samplerate=self.samplerate,
					channels=self.channels,
					dtype='int16',
					callback=self._audio_callback,
					blocksize=blocksize
				)
			else:
				self.stream = sd.InputStream(
					samplerate=self.samplerate,
					channels=self.channels,
					dtype='int16',
					callback=self._audio_callback,
					blocksize=blocksize
				)
			self.stream.start()
			print(f"Audio stream started (device={self.device_id})")
		except Exception as e:
			print(f"Error starting audio stream: {e}")

	def _audio_callback(self, indata, frames, time, status):
		if status:
			print(status)
		# push a copy to the asyncio queue in a thread-safe way
		self.loop.call_soon_threadsafe(self.q.put_nowait, indata.copy())

	def stop_recording(self):
		print("Stopping audio recording...")
		if self.stream:
			self.stream.stop()
			self.stream.close()

	async def recv(self):
		from av import AudioFrame
		# wait for next chunk
		data = await self.q.get()
		# data shape: (samples, channels)
		samples = data.shape[0]
		layout = 'mono' if self.channels == 1 else 'stereo'
		frame = AudioFrame(format='s16', layout=layout, samples=samples)
		frame.planes[0].update(data.tobytes())
		frame.sample_rate = self.samplerate

		# set pts/time_base based on sample count
		frame.pts = self._pts
		frame.time_base = fractions.Fraction(1, self.samplerate)
		self._pts += samples
		return frame

	async def stop(self):
		self.stop_recording()
		print("Audio track stopped.")

# 画面キャプチャ用VideoStreamTrack
class ScreenTrack(VideoStreamTrack):
	def __init__(self, fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX):
		super().__init__()
		self.sct = mss.mss()
		self.monitor = self.sct.monitors[monitor_index]
		self.fps = fps
		self.frame_time = 1.0 / fps
		self._last_frame = 0

	async def recv(self):
		from av import VideoFrame
		pts, time_base = await self.next_timestamp()
		# フレームレート制御
		now = asyncio.get_event_loop().time()
		wait = self._last_frame + self.frame_time - now
		if wait > 0:
			await asyncio.sleep(wait)
		self._last_frame = asyncio.get_event_loop().time()
		img = np.array(self.sct.grab(self.monitor))
		frame = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
		video_frame = VideoFrame.from_ndarray(frame, format="bgr24")
		video_frame.pts = pts
		video_frame.time_base = time_base
		return video_frame

# シグナリングサーバー
pcs = set()

async def offer(websocket, path):
    try:
        params = await websocket.recv()
        params = json.loads(params)

        # Validate SDP parameters
        if "sdp" not in params or "type" not in params:
            print("Invalid SDP parameters received")
            return

        offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

        pc = RTCPeerConnection()
        pcs.add(pc)
        print("Created for", path)

        # 画面キャプチャトラックを追加
        screen_track = ScreenTrack(fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX)
        pc.addTrack(screen_track)

        # 音声キャプチャトラックを追加
        audio_track = SystemAudioTrack()
        audio_track.start_recording()  # Start recording when client connects
        pc.addTrack(audio_track)

        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await websocket.send(json.dumps({"type": "candidate", "candidate": candidate}))

        # クライアントからのICE candidate受信
        async def ice_listener():
            while True:
                try:
                    msg = await websocket.recv()
                    msg = json.loads(msg)
                    if msg["type"] == "candidate":
                        await pc.addIceCandidate(msg["candidate"])
                except Exception:
                    break

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)
        await websocket.send(json.dumps({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}))

        # ICE candidateの受信を別タスクで
        asyncio.ensure_future(ice_listener())

        # 接続維持
        await websocket.wait_closed()
        await audio_track.stop()  # Stop recording when client disconnects
        await pc.close()
        pcs.discard(pc)

    except Exception as e:
        print("Error in offer handler:", e)

async def main():
	async with websockets.serve(offer, SERVER_IP, 8765):
		print(f"Signaling server started on ws://{SERVER_IP}:8765")
		await asyncio.Future()  # run forever

if __name__ == "__main__":
	asyncio.run(main())
