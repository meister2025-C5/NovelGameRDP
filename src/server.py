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



# 画面キャプチャ設定
SCREEN_FPS = 30  # キャプチャフレームレート
SCREEN_MONITOR_INDEX = 1  # mssのmonitor番号（1=メイン画面）

# 音声キャプチャ設定
AUDIO_DEVICE_NAME = "ステレオ ミキサー (Realtek(R) Audio)"  # デバイス名
AUDIO_HOSTAPI = "WASAPI"  # MMEを明示
AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNELS = 1
AUDIO_BLOCKSIZE = 960  # 20ms @ 48kHz
# 音声キャプチャ用AudioStreamTrack


class SystemAudioTrack(AudioStreamTrack):
	kind = "audio"
	def __init__(self, device_name=AUDIO_DEVICE_NAME, hostapi=AUDIO_HOSTAPI, samplerate=AUDIO_SAMPLE_RATE, channels=AUDIO_CHANNELS, blocksize=AUDIO_BLOCKSIZE):
		super().__init__()
		self.device_name = device_name
		self.hostapi = hostapi
		self.samplerate = samplerate
		self.channels = channels
		self.blocksize = blocksize
		self.buffer = asyncio.Queue(maxsize=10)
		self._stop_event = threading.Event()
		self._thread = threading.Thread(target=self._audio_thread, daemon=True)
		self._thread.start()
		# ここはasync関数内で呼ぶ必要あり
		try:
			self.loop = asyncio.get_running_loop()
		except RuntimeError:
			self.loop = asyncio.get_event_loop()  # ここでループを保存

	def _find_device_index(self):
		devices = sd.query_devices()
		for idx, dev in enumerate(devices):
			if dev['name'] == self.device_name and sd.query_hostapis(dev['hostapi'])['name'] == self.hostapi:
				return idx
		raise RuntimeError(f"Device '{self.device_name}' with hostapi '{self.hostapi}' not found.")

	def _audio_thread(self):
		def callback(indata, frames, time, status):
			if status:
				print("Audio status:", status)
			pcm16 = (indata * 32767).astype(np.int16).tobytes()
			try:
				# asyncio.run_coroutine_threadsafe(self.buffer.put(pcm16), self.loop)
				fut = asyncio.run_coroutine_threadsafe(self.buffer.put(pcm16), self.loop)
				fut.result()  # 例外をここで拾う（オプション）
			except RuntimeError:
				pass

		try:
			device_index = self._find_device_index()
			with sd.InputStream(device=device_index, samplerate=self.samplerate, channels=self.channels, blocksize=self.blocksize, dtype='float32', callback=callback):
				self._stop_event.wait()
		except Exception as e:
			print("Audio input error:", e)

	async def recv(self):
		from av import AudioFrame
		pcm = await self.buffer.get()
		frame = AudioFrame(format="s16", layout="stereo" if self.channels == 2 else "mono", samples=self.blocksize)
		frame.planes[0].update(pcm)
		frame.sample_rate = self.samplerate
		return frame

	async def stop(self):
		self._stop_event.set()
		await super().stop()

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
	params = await websocket.recv()
	params = json.loads(params)
	offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

	pc = RTCPeerConnection()
	pcs.add(pc)
	print("Created for", path)


	# 画面キャプチャトラックを追加
	screen_track = ScreenTrack(fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX)
	pc.addTrack(screen_track)

	# 音声キャプチャトラックを追加
	audio_track = SystemAudioTrack()
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
	await pc.close()
	pcs.discard(pc)

async def main():
	async with websockets.serve(offer, "0.0.0.0", 8765):
		print("Signaling server started on ws://0.0.0.0:8765")
		await asyncio.Future()  # run forever

if __name__ == "__main__":
	asyncio.run(main())
