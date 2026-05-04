/**
 * XState v5 conversation state machine for the voice interview pipeline.
 *
 * States:
 *   idle        — waiting for audio to be enabled or session to load
 *   listening   — VAD is active, waiting for user to speak
 *   capturing   — VAD detected speech, recording until onSpeechEnd
 *   processing  — sending WAV to STT, waiting for transcript
 *   thinking    — LLM + TTS streaming in progress
 *   speaking    — audio is playing back
 *   interrupted — user spoke during playback; stopping audio + aborting fetch
 *
 * Key events:
 *   ENABLE / DISABLE          — toggle voice pipeline
 *   SPEECH_START              — VAD detected user speech
 *   SPEECH_END { audio }      — VAD complete utterance
 *   TRANSCRIPT { text }       — STT returned text
 *   STREAM_STARTED            — converse/stream fetch began
 *   PLAYBACK_STARTED          — first audio chunk scheduled
 *   PLAYBACK_DONE             — all scheduled audio finished
 *   INTERRUPT                 — explicit interrupt (e.g., button press)
 *   ERROR { message }         — any pipeline error
 */

import { setup, assign } from "xstate"

export interface ConversationContext {
  /** Monotonically increasing ID to guard against stale events. */
  replyId: number
  /** Latest transcript from STT. */
  transcript: string
  /** AbortController for the current converse/stream fetch. */
  abortController: AbortController | null
  /** Latest error message. */
  error: string | null
}

export type ConversationEvent =
  | { type: "ENABLE" }
  | { type: "DISABLE" }
  | { type: "SPEECH_START" }
  | { type: "SPEECH_END"; audio: Float32Array }
  | { type: "TRANSCRIPT"; text: string; replyId: number }
  | { type: "STREAM_STARTED"; abortController: AbortController; replyId: number }
  | { type: "PLAYBACK_STARTED"; replyId: number }
  | { type: "PLAYBACK_DONE"; replyId: number }
  | { type: "INTERRUPT" }
  | { type: "ERROR"; message: string }

export const conversationMachine = setup({
  types: {
    context: {} as ConversationContext,
    events: {} as ConversationEvent,
  },
  guards: {
    matchesReplyId: ({ context, event }) => {
      if ("replyId" in event) {
        return event.replyId === context.replyId
      }
      return true
    },
  },
  actions: {
    incrementReplyId: assign({
      replyId: ({ context }) => context.replyId + 1,
    }),
    setTranscript: assign({
      transcript: ({ event }) => {
        if (event.type === "TRANSCRIPT") return event.text
        return ""
      },
    }),
    setAbortController: assign({
      abortController: ({ event }) => {
        if (event.type === "STREAM_STARTED") return event.abortController
        return null
      },
    }),
    abortFetch: ({ context }) => {
      context.abortController?.abort()
    },
    clearAbortController: assign({
      abortController: () => null,
    }),
    setError: assign({
      error: ({ event }) => {
        if (event.type === "ERROR") return event.message
        return null
      },
    }),
    clearError: assign({
      error: () => null,
    }),
  },
}).createMachine({
  id: "conversation",
  initial: "idle",
  context: {
    replyId: 0,
    transcript: "",
    abortController: null,
    error: null,
  },
  states: {
    idle: {
      on: {
        ENABLE: { target: "listening", actions: "clearError" },
      },
    },
    listening: {
      on: {
        SPEECH_START: "capturing",
        DISABLE: "idle",
        // Allow direct transition to thinking (e.g., for opening message)
        STREAM_STARTED: {
          target: "thinking",
          actions: ["incrementReplyId", "setAbortController"],
        },
      },
    },
    capturing: {
      on: {
        SPEECH_END: {
          target: "processing",
          actions: "incrementReplyId",
        },
        DISABLE: "idle",
      },
    },
    processing: {
      on: {
        TRANSCRIPT: {
          target: "thinking",
          guard: "matchesReplyId",
          actions: "setTranscript",
        },
        ERROR: {
          target: "listening",
          actions: "setError",
        },
        DISABLE: "idle",
      },
    },
    thinking: {
      on: {
        STREAM_STARTED: {
          actions: "setAbortController",
          guard: "matchesReplyId",
        },
        PLAYBACK_STARTED: {
          target: "speaking",
          guard: "matchesReplyId",
        },
        PLAYBACK_DONE: {
          target: "listening",
          guard: "matchesReplyId",
          actions: "clearAbortController",
        },
        // User speaks during thinking — interrupt
        SPEECH_START: "interrupted",
        INTERRUPT: "interrupted",
        ERROR: {
          target: "listening",
          actions: ["setError", "clearAbortController"],
        },
        DISABLE: {
          target: "idle",
          actions: ["abortFetch", "clearAbortController"],
        },
      },
    },
    speaking: {
      on: {
        PLAYBACK_DONE: {
          target: "listening",
          guard: "matchesReplyId",
          actions: "clearAbortController",
        },
        SPEECH_START: "interrupted",
        INTERRUPT: "interrupted",
        ERROR: {
          target: "listening",
          actions: ["setError", "clearAbortController"],
        },
        DISABLE: {
          target: "idle",
          actions: ["abortFetch", "clearAbortController"],
        },
      },
    },
    interrupted: {
      entry: ["abortFetch", "clearAbortController"],
      always: "capturing",
    },
  },
})
