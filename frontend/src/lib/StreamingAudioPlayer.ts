/**
 * StreamingAudioPlayer — gapless playback of streaming MP3 chunks
 * with AnalyserNode for lip-sync and 20ms fade-out on interruption.
 *
 * Architecture:
 *   AudioBufferSourceNode queue → GainNode → AnalyserNode → destination
 *
 * Each decoded MP3 blob is scheduled precisely using `source.start(nextStartTime)`
 * for gapless playback. The AnalyserNode taps all flowing audio and provides
 * RMS amplitude data for lip-sync rendering.
 */

export class StreamingAudioPlayer {
  readonly ctx: AudioContext
  readonly analyser: AnalyserNode
  private readonly gain: GainNode
  private readonly scheduled: Set<AudioBufferSourceNode> = new Set()
  private nextStartTime = 0
  private _playing = false

  /** Buffer for AnalyserNode time-domain data */
  readonly timeDomainBuffer: Uint8Array

  constructor(ctx?: AudioContext) {
    this.ctx = ctx ?? new AudioContext({ latencyHint: "interactive" })

    this.gain = this.ctx.createGain()
    this.analyser = this.ctx.createAnalyser()
    this.analyser.fftSize = 256
    this.analyser.smoothingTimeConstant = 0 // only affects frequency data, not time-domain

    this.gain.connect(this.analyser)
    this.analyser.connect(this.ctx.destination)

    this.timeDomainBuffer = new Uint8Array(this.analyser.frequencyBinCount)
  }

  get playing(): boolean {
    return this._playing
  }

  /** Resume AudioContext if suspended (browser autoplay policy). */
  async ensureResumed(): Promise<void> {
    if (this.ctx.state === "suspended") {
      await this.ctx.resume()
    }
  }

  /**
   * Schedule an MP3 blob for gapless playback.
   * Call this for each MP3 chunk received from the streaming response.
   */
  async scheduleChunk(mp3Bytes: ArrayBuffer): Promise<void> {
    await this.ensureResumed()

    let audioBuffer: AudioBuffer
    try {
      // decodeAudioData needs a copy — the original may be detached
      const copy = mp3Bytes.slice(0)
      audioBuffer = await this.ctx.decodeAudioData(copy)
    } catch (err) {
      console.warn("[StreamingAudioPlayer] Failed to decode chunk:", err)
      return
    }

    const source = this.ctx.createBufferSource()
    source.buffer = audioBuffer
    source.connect(this.gain)
    this.scheduled.add(source)

    source.onended = () => {
      try { source.disconnect() } catch { /* ignore */ }
      this.scheduled.delete(source)
      if (this.scheduled.size === 0) {
        this._playing = false
        this.nextStartTime = 0
        this.onPlaybackDone?.()
      }
    }

    const startAt = Math.max(this.ctx.currentTime + 0.02, this.nextStartTime)
    source.start(startAt)
    this.nextStartTime = startAt + audioBuffer.duration
    this._playing = true
  }

  /**
   * Stop all playback with a 20ms linear gain fade to avoid clicks.
   * Returns a promise that resolves after the fade completes.
   */
  async stop(): Promise<void> {
    if (this.scheduled.size === 0) {
      this._playing = false
      return
    }

    const now = this.ctx.currentTime
    const fadeEnd = now + 0.020

    // Ramp gain to zero
    this.gain.gain.cancelScheduledValues(now)
    this.gain.gain.setValueAtTime(this.gain.gain.value, now)
    this.gain.gain.linearRampToValueAtTime(0, fadeEnd)

    // Stop and disconnect all scheduled sources after fade
    for (const src of this.scheduled) {
      try { src.stop(fadeEnd) } catch { /* ignore */ }
      try { src.disconnect() } catch { /* ignore */ }
    }
    this.scheduled.clear()
    this.nextStartTime = 0
    this._playing = false

    // Wait for fade to complete
    await new Promise((r) => setTimeout(r, 25))

    // Restore gain for next playback
    this.gain.gain.cancelScheduledValues(this.ctx.currentTime)
    this.gain.gain.setValueAtTime(1, this.ctx.currentTime)
  }

  /**
   * Compute RMS amplitude from the AnalyserNode's time-domain data.
   * Returns a value in [0, 1] suitable for lip-sync rendering.
   */
  computeRMS(): number {
    this.analyser.getByteTimeDomainData(this.timeDomainBuffer)
    let sumSq = 0
    for (let i = 0; i < this.timeDomainBuffer.length; i++) {
      const v = (this.timeDomainBuffer[i] - 128) / 128 // centered on 0
      sumSq += v * v
    }
    // Scale by 3 — typical speech RMS is 0.05–0.2
    return Math.min(1, Math.sqrt(sumSq / this.timeDomainBuffer.length) * 3.0)
  }

  /** Optional callback fired when all scheduled audio finishes. */
  onPlaybackDone: (() => void) | null = null

  /** Clean up all resources. */
  destroy(): void {
    void this.stop()
    try { this.gain.disconnect() } catch { /* ignore */ }
    try { this.analyser.disconnect() } catch { /* ignore */ }
    // Don't close the AudioContext — it may be shared
  }
}
