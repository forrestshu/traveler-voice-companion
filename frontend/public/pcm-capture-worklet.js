// 音频采集层：把浏览器麦克风采样重采样到火山引擎要求的 16 kHz Int16 PCM。
class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = [];
    this.targetRate = 16000;
  }

  process(inputs) {
    const channel = inputs[0]?.[0];
    if (!channel) return true;

    const ratio = sampleRate / this.targetRate;
    const outputLength = Math.floor(channel.length / ratio);
    const pcm = new Int16Array(outputLength);
    for (let index = 0; index < outputLength; index += 1) {
      const sourceIndex = Math.floor(index * ratio);
      const sample = Math.max(-1, Math.min(1, channel[sourceIndex]));
      pcm[index] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
    }
    this.port.postMessage(pcm.buffer, [pcm.buffer]);
    return true;
  }
}

registerProcessor("pcm-capture", PcmCaptureProcessor);

