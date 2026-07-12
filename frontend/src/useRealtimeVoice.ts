import { useCallback, useEffect, useRef, useState } from "react";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "listening"
  | "thinking"
  | "speaking"
  | "error";

export type ChatMessage = {
  id: string;
  role: "traveler" | "paimon";
  text: string;
  interim: boolean;
};

type ServerEvent = {
  event: string;
  value?: ConnectionState;
  role?: "traveler" | "paimon";
  text?: string;
  interim?: boolean;
  message?: string;
};

// 音频播放队列：把连续到达的 24 kHz PCM 安排到同一时间轴，避免块间爆音。
function createPcmPlayer(context: AudioContext) {
  let nextStartTime = context.currentTime;

  return {
    enqueue(arrayBuffer: ArrayBuffer) {
      const input = new Int16Array(arrayBuffer);
      const float32 = new Float32Array(input.length);
      for (let index = 0; index < input.length; index += 1) {
        float32[index] = input[index] / 0x8000;
      }
      const buffer = context.createBuffer(1, float32.length, 24000);
      buffer.copyToChannel(float32, 0);
      const source = context.createBufferSource();
      source.buffer = buffer;
      source.connect(context.destination);
      nextStartTime = Math.max(nextStartTime, context.currentTime + 0.04);
      source.start(nextStartTime);
      nextStartTime += buffer.duration;
    },
    reset() {
      nextStartTime = context.currentTime;
    },
  };
}

// 实时会话 Hook：统一管理麦克风、WebSocket、字幕和 PCM 播放状态。
export function useRealtimeVoice() {
  const [state, setState] = useState<ConnectionState>("idle");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [error, setError] = useState("");
  const [muted, setMuted] = useState(false);
  const mutedRef = useRef(false);
  const socketRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletRef = useRef<AudioWorkletNode | null>(null);
  const playerRef = useRef<ReturnType<typeof createPcmPlayer> | null>(null);

  // 字幕状态转换：临时结果覆盖同一角色的末条消息，最终结果才固定到历史记录。
  const mergeTranscript = useCallback((event: ServerEvent) => {
    if (!event.role || !event.text) return;
    const text = event.text;
    setMessages((current) => {
      const last = current.at(-1);
      if (last && last.role === event.role && last.interim) {
        // 用户 ASR 返回的是整句修订，AI ChatResponse 返回的是增量片段。
        const nextText = event.role === "paimon" ? last.text + text : text;
        return [
          ...current.slice(0, -1),
          { ...last, text: nextText, interim: event.interim ?? true },
        ];
      }
      return [
        ...current,
        {
          id: crypto.randomUUID(),
          role: event.role!,
          text,
          interim: event.interim ?? true,
        },
      ];
    });
  }, []);

  // 停止会话：按顺序关闭采集节点、麦克风轨道、音频上下文和本地连接。
  const stop = useCallback(() => {
    const socket = socketRef.current;
    if (socket?.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "finish" }));
      socket.close();
    }
    workletRef.current?.disconnect();
    sourceRef.current?.disconnect();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    void audioContextRef.current?.close();
    socketRef.current = null;
    streamRef.current = null;
    audioContextRef.current = null;
    playerRef.current = null;
    setMuted(false);
    mutedRef.current = false;
    setState("idle");
  }, []);

  // 开始会话：用户手势同时解锁麦克风和音频播放，再等待云端 ready 后发送 PCM。
  const start = useCallback(async () => {
    setError("");
    setState("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      const audioContext = new AudioContext();
      await audioContext.resume();
      await audioContext.audioWorklet.addModule("/pcm-capture-worklet.js");
      const source = audioContext.createMediaStreamSource(stream);
      const worklet = new AudioWorkletNode(audioContext, "pcm-capture");
      const silentGain = audioContext.createGain();
      silentGain.gain.value = 0;
      source.connect(worklet).connect(silentGain).connect(audioContext.destination);

      const scheme = location.protocol === "https:" ? "wss" : "ws";
      // 部署时使用 Render 的公网 WSS；本地开发仍通过 Vite 代理连接 FastAPI。
      const socketUrl =
        import.meta.env.VITE_REALTIME_WS_URL ||
        `${scheme}://${location.host}/ws/conversation`;
      const socket = new WebSocket(socketUrl);
      socket.binaryType = "arraybuffer";

      streamRef.current = stream;
      audioContextRef.current = audioContext;
      sourceRef.current = source;
      workletRef.current = worklet;
      socketRef.current = socket;
      playerRef.current = createPcmPlayer(audioContext);

      let cloudReady = false;
      worklet.port.onmessage = ({ data }: MessageEvent<ArrayBuffer>) => {
        if (cloudReady && !mutedRef.current && socket.readyState === WebSocket.OPEN) {
          socket.send(data);
        }
      };
      socket.onmessage = (message) => {
        if (message.data instanceof ArrayBuffer) {
          playerRef.current?.enqueue(message.data);
          return;
        }
        const event = JSON.parse(message.data) as ServerEvent;
        if (event.event === "ready") {
          cloudReady = true;
          setState("listening");
        } else if (event.event === "status" && event.value) {
          setState(event.value);
        } else if (event.event === "transcript") {
          mergeTranscript(event);
        } else if (event.event === "transcript_end") {
          setMessages((current) =>
            current.map((item, index) =>
              index === current.length - 1 ? { ...item, interim: false } : item,
            ),
          );
        } else if (event.event === "error") {
          setError(event.message || "实时服务发生未知错误");
          setState("error");
        }
      };
      socket.onerror = () => {
        setError("无法连接本地实时语音服务");
        setState("error");
      };
      socket.onclose = () => {
        if (state !== "idle") setState("idle");
      };
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "无法使用麦克风");
      setState("error");
    }
  }, [mergeTranscript, state]);

  // 打断：立即清空本地播放时间轴，并通知云端停止当前回答。
  const interrupt = useCallback(() => {
    playerRef.current?.reset();
    socketRef.current?.send(JSON.stringify({ type: "interrupt" }));
    setState("listening");
  }, []);

  // 静音只控制上行音频，连接保持，避免重新建立昂贵会话。
  const toggleMute = useCallback(() => {
    setMuted((value) => {
      mutedRef.current = !value;
      return !value;
    });
  }, []);

  useEffect(() => stop, [stop]);

  return { state, messages, error, muted, start, stop, interrupt, toggleMute };
}
