import { vi } from "vitest";

type MockResultEvent = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: {
      isFinal: boolean;
      0: {
        transcript: string;
      };
    };
  };
};

export class MockSpeechRecognition {
  static instances: MockSpeechRecognition[] = [];

  continuous = false;
  interimResults = false;
  lang = "en-US";
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: ((event: { error?: string }) => void) | null = null;
  onresult: ((event: MockResultEvent) => void) | null = null;

  constructor() {
    MockSpeechRecognition.instances.push(this);
  }

  start() {
    this.onstart?.();
  }

  stop() {
    this.onend?.();
  }

  emitTranscript(transcript: string, isFinal = true) {
    this.onresult?.({
      resultIndex: 0,
      results: {
        length: 1,
        0: {
          isFinal,
          0: {
            transcript,
          },
        },
      },
    });
    if (isFinal) {
      this.onend?.();
    }
  }
}

export class MockSpeechSynthesisUtterance {
  text: string;
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;

  constructor(text: string) {
    this.text = text;
  }
}

export function installVoiceTestStubs() {
  MockSpeechRecognition.instances = [];
  const speak = vi.fn((utterance: MockSpeechSynthesisUtterance) => {
    utterance.onstart?.();
    utterance.onend?.();
  });
  const cancel = vi.fn();
  const speechSynthesis = { speak, cancel };

  Object.defineProperty(window, "SpeechRecognition", {
    configurable: true,
    writable: true,
    value: MockSpeechRecognition,
  });
  Object.defineProperty(window, "webkitSpeechRecognition", {
    configurable: true,
    writable: true,
    value: MockSpeechRecognition,
  });
  Object.defineProperty(window, "speechSynthesis", {
    configurable: true,
    writable: true,
    value: speechSynthesis,
  });
  vi.stubGlobal("SpeechSynthesisUtterance", MockSpeechSynthesisUtterance);

  return { speak, cancel, speechSynthesis };
}
