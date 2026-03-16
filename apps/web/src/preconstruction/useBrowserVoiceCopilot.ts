import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type SpeechRecognitionAlternativeLike = {
  transcript?: string;
};

type SpeechRecognitionResultLike = {
  isFinal?: boolean;
  0?: SpeechRecognitionAlternativeLike;
};

type SpeechRecognitionResultListLike = {
  length: number;
  [index: number]: SpeechRecognitionResultLike;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: SpeechRecognitionResultListLike;
};

type SpeechRecognitionErrorEventLike = {
  error?: string;
};

type BrowserSpeechRecognitionLike = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  start: () => void;
  stop: () => void;
};

type BrowserSpeechRecognitionConstructor = new () => BrowserSpeechRecognitionLike;

type VoiceWindow = Window & {
  SpeechRecognition?: BrowserSpeechRecognitionConstructor;
  webkitSpeechRecognition?: BrowserSpeechRecognitionConstructor;
};

type UseBrowserVoiceCopilotOptions = {
  onFinalTranscript: (transcript: string) => void;
  onInterimTranscript?: (transcript: string) => void;
};

function getRecognitionConstructor(): BrowserSpeechRecognitionConstructor | null {
  if (typeof window === "undefined") return null;
  const voiceWindow = window as VoiceWindow;
  return voiceWindow.SpeechRecognition ?? voiceWindow.webkitSpeechRecognition ?? null;
}

function normalizeVoiceError(code?: string): string {
  switch (code) {
    case "audio-capture":
      return "Voice input could not access a microphone.";
    case "network":
      return "Voice input failed because speech recognition is unavailable right now.";
    case "not-allowed":
    case "service-not-allowed":
      return "Voice input is blocked until microphone access is allowed.";
    case "no-speech":
      return "No speech was detected. Try again when you are ready.";
    case "aborted":
      return "Voice input was stopped before a final transcript was captured.";
    default:
      return "Voice input failed. Try again or continue with typed input.";
  }
}

export function useBrowserVoiceCopilot({
  onFinalTranscript,
  onInterimTranscript,
}: UseBrowserVoiceCopilotOptions) {
  const recognitionRef = useRef<BrowserSpeechRecognitionLike | null>(null);
  const recognitionSupported = useMemo(() => getRecognitionConstructor() != null, []);
  const speechOutputSupported = useMemo(
    () => typeof window !== "undefined" && typeof window.speechSynthesis !== "undefined",
    []
  );
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);
  const [interimTranscript, setInterimTranscript] = useState("");
  const [voiceError, setVoiceError] = useState("");

  const clearVoiceError = useCallback(() => {
    setVoiceError("");
  }, []);

  const stopListening = useCallback(() => {
    recognitionRef.current?.stop();
    setIsListening(false);
  }, []);

  const stopSpeaking = useCallback(() => {
    if (!speechOutputSupported) return;
    window.speechSynthesis.cancel();
    setIsSpeaking(false);
  }, [speechOutputSupported]);

  const speakText = useCallback(
    (text: string): boolean => {
      const message = text.trim();
      if (!message) return false;
      if (!speechOutputSupported || typeof SpeechSynthesisUtterance === "undefined") {
        setVoiceError("Voice output is not available in this browser.");
        return false;
      }

      const utterance = new SpeechSynthesisUtterance(message);
      utterance.onstart = () => {
        setVoiceError("");
        setIsSpeaking(true);
      };
      utterance.onend = () => {
        setIsSpeaking(false);
      };
      utterance.onerror = () => {
        setIsSpeaking(false);
        setVoiceError("Voice output failed. You can still read the copilot response below.");
      };
      window.speechSynthesis.cancel();
      window.speechSynthesis.speak(utterance);
      return true;
    },
    [speechOutputSupported]
  );

  const startListening = useCallback(() => {
    const Recognition = getRecognitionConstructor();
    if (!Recognition) {
      setVoiceError("Voice input is not available in this browser.");
      return;
    }

    stopSpeaking();

    const recognition = new Recognition();
    recognitionRef.current = recognition;
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";
    recognition.onstart = () => {
      setVoiceError("");
      setInterimTranscript("");
      onInterimTranscript?.("");
      setIsListening(true);
    };
    recognition.onresult = (event) => {
      let nextInterim = "";
      let nextFinal = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const transcript = result?.[0]?.transcript?.trim() ?? "";
        if (!transcript) continue;
        if (result?.isFinal) {
          nextFinal += `${nextFinal ? " " : ""}${transcript}`;
        } else {
          nextInterim += `${nextInterim ? " " : ""}${transcript}`;
        }
      }

      setInterimTranscript(nextInterim);
      onInterimTranscript?.(nextInterim);

      if (nextFinal) {
        setInterimTranscript("");
        onInterimTranscript?.("");
        onFinalTranscript(nextFinal);
      }
    };
    recognition.onerror = (event) => {
      setVoiceError(normalizeVoiceError(event.error));
    };
    recognition.onend = () => {
      setIsListening(false);
    };

    try {
      recognition.start();
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : "Unable to start voice input.");
      setIsListening(false);
    }
  }, [onFinalTranscript, onInterimTranscript, stopSpeaking]);

  useEffect(() => {
    return () => {
      recognitionRef.current?.stop();
      if (speechOutputSupported) {
        window.speechSynthesis.cancel();
      }
    };
  }, [speechOutputSupported]);

  return {
    recognitionSupported,
    speechOutputSupported,
    isListening,
    isSpeaking,
    interimTranscript,
    voiceError,
    clearVoiceError,
    startListening,
    stopListening,
    speakText,
    stopSpeaking,
  };
}
