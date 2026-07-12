import { Mic, MicOff, PhoneOff, Sparkles, Volume2 } from "lucide-react";
import { useEffect, useRef } from "react";
import { useRealtimeVoice, type ConnectionState } from "./useRealtimeVoice";

const stateCopy: Record<ConnectionState, string> = {
  idle: "等待同行",
  connecting: "正在穿过星海…",
  listening: "派蒙在听",
  thinking: "派蒙想一想",
  speaking: "派蒙正在回答",
  error: "连接遇到问题",
};

// 主界面组件：人物是视觉中心，聊天记录和通话控件保持在边缘区域。
export default function App() {
  const { state, messages, error, muted, start, stop, interrupt, toggleMute } =
    useRealtimeVoice();
  const transcriptRef = useRef<HTMLDivElement>(null);
  const active = !["idle", "error"].includes(state);

  // 新字幕出现后只滚动聊天区域，不移动整张沉浸式场景。
  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  return (
    <main className={`scene scene--${state}`}>
      <video
        className="scene__ambient"
        src="/companion.mp4"
        autoPlay
        loop
        muted
        playsInline
        aria-hidden="true"
      />
      <div className="scene__veil" aria-hidden="true" />

      <header className="topbar">
        <div className="brand">
          <Sparkles size={17} aria-hidden="true" />
          <span>旅途回声</span>
        </div>
        <div className="status" role="status" aria-live="polite">
          <span className="status__dot" aria-hidden="true" />
          {stateCopy[state]}
        </div>
      </header>

      <section className="portrait" aria-label="对话伙伴">
        <div className="portrait__halo" aria-hidden="true" />
        <video
          className="portrait__video"
          src="/companion.mp4"
          autoPlay
          loop
          muted
          playsInline
        />
        <div className="portrait__signal" aria-hidden="true">
          {Array.from({ length: 5 }).map((_, index) => (
            <i key={index} />
          ))}
        </div>
      </section>

      <aside className="conversation" aria-label="实时对话字幕">
        <div className="conversation__heading">
          <span>此刻的对话</span>
          <span>{messages.length ? `${messages.length} 条` : "尚未开始"}</span>
        </div>
        <div className="conversation__scroll" ref={transcriptRef}>
          {messages.length === 0 ? (
            <p className="conversation__empty">
              开始后直接说话。派蒙会称呼你为旅行者，并用复刻音色回应。
            </p>
          ) : (
            messages.map((message) => (
              <article
                className={`message message--${message.role}`}
                key={message.id}
              >
                <span>{message.role === "paimon" ? "派蒙" : "旅行者"}</span>
                <p>{message.text}</p>
              </article>
            ))
          )}
        </div>
      </aside>

      <footer className="controls">
        {!active ? (
          <button className="button button--start" onClick={() => void start()}>
            <Mic size={20} aria-hidden="true" />
            开始对话
          </button>
        ) : (
          <>
            <button
              className="button button--round"
              onClick={toggleMute}
              aria-label={muted ? "取消麦克风静音" : "静音麦克风"}
              aria-pressed={muted}
            >
              {muted ? <MicOff /> : <Mic />}
            </button>
            <button className="button button--interrupt" onClick={interrupt}>
              <Volume2 size={19} aria-hidden="true" />
              打断
            </button>
            <button
              className="button button--round button--end"
              onClick={stop}
              aria-label="结束对话"
            >
              <PhoneOff />
            </button>
          </>
        )}
      </footer>

      {error && (
        <div className="error-banner" role="alert">
          {error}
        </div>
      )}
    </main>
  );
}

