// Data-over-sound wrapper around ggwave (MIT). Same approach that passed the spike (spike/sound-test).
// One ggwave instance per page: two instances crashed the WASM module in the spike.
const Sound = (() => {
  let ggwave = null, instance = null, ctx = null;
  const ready = ggwave_factory().then(m => { ggwave = m; });

  function ensureAudio() {
    if (!ggwave) throw new Error("Sound engine is still loading — try again in a second");
    if (!ctx) {
      ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 48000 });
      const p = ggwave.getDefaultParameters();
      p.sampleRateInp = ctx.sampleRate;
      p.sampleRateOut = ctx.sampleRate;
      instance = ggwave.init(p);
    }
    if (ctx.state === "suspended") ctx.resume(); // iOS needs a user gesture
  }

  // ggwave works on raw bytes; reinterpret the same memory as another typed array
  function convert(src, Type) {
    const buf = new ArrayBuffer(src.byteLength);
    new src.constructor(buf).set(src);
    return new Type(buf);
  }

  // Plays `token` through the speakers. Returns the duration in seconds.
  function broadcast(token, protocol = "GGWAVE_PROTOCOL_ULTRASOUND_NORMAL", volume = 50) {
    ensureAudio();
    const wave = ggwave.encode(instance, token, ggwave.ProtocolId[protocol], volume);
    const samples = convert(wave, Float32Array);
    const buffer = ctx.createBuffer(1, samples.length, ctx.sampleRate);
    buffer.getChannelData(0).set(samples);
    const src = ctx.createBufferSource();
    src.buffer = buffer;
    src.connect(ctx.destination);
    src.start(0);
    return samples.length / ctx.sampleRate;
  }

  // Starts the microphone and calls onToken(text) for every plausible decoded token.
  async function listen(onToken) {
    ensureAudio();
    if (!window.isSecureContext) throw new Error("The microphone needs HTTPS — open the https:// link.");
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: false, autoGainControl: false, noiseSuppression: false }
    });
    const input = ctx.createMediaStreamSource(stream);
    const proc = ctx.createScriptProcessor(1024, 1, 1);
    proc.onaudioprocess = e => {
      const chunk = new Float32Array(e.inputBuffer.getChannelData(0));
      const res = ggwave.decode(instance, convert(chunk, Int8Array));
      if (res && res.length > 0) {
        const text = new TextDecoder("utf-8").decode(res);
        // Spike finding: ggwave can return corrupted bytes without an error, so check the shape first.
        // The server is still the judge — it rejects any token it did not just issue.
        if (/^[A-Z0-9]{4,12}$/.test(text)) onToken(text);
      }
    };
    input.connect(proc);
    proc.connect(ctx.destination);
    window.__keepAlive = [stream, input, proc]; // stop the garbage collector from killing the mic graph
  }

  // Browsers only allow audio after a user gesture; call this from a click handler.
  const unlock = () => { try { ensureAudio(); } catch {} };

  return { ready, broadcast, listen, unlock };
})();

// Small helpers shared by both pages
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
async function api(url, body) {
  const opts = body === undefined ? {} :
    body instanceof FormData ? { method: "POST", body } :
    { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const r = await fetch(url, opts);
  const data = await r.json().catch(() => ({}));
  if (!r.ok && data.ok === undefined) data.ok = false;
  return data;
}
