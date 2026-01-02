# 必要なパッケージ: aiortc, websockets, mss, opencv-python, av
import asyncio
import json
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack
from aiortc.contrib.media import MediaRelay
import cv2
import numpy as np
import mss


# 画面キャプチャ設定
SCREEN_FPS = 30  # キャプチャフレームレート
SCREEN_MONITOR_INDEX = 1  # mssのmonitor番号（1=メイン画面）

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
relay = MediaRelay()

async def offer(websocket, path):
	params = await websocket.recv()
	params = json.loads(params)
	offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

	pc = RTCPeerConnection()
	pcs.add(pc)
	print("Created for", path)

	# 画面キャプチャトラックを追加
	screen_track = ScreenTrack(fps=SCREEN_FPS, monitor_index=SCREEN_MONITOR_INDEX)
	pc.addTrack(relay.subscribe(screen_track))

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
	await pc._connection_state_complete.wait()
	await websocket.wait_closed()
	await pc.close()
	pcs.discard(pc)

async def main():
	async with websockets.serve(offer, "0.0.0.0", 8765):
		print("Signaling server started on ws://0.0.0.0:8765")
		await asyncio.Future()  # run forever

if __name__ == "__main__":
	asyncio.run(main())
