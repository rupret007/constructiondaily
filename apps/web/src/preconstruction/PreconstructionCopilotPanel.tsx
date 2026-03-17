import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { queryPreconstructionCopilot } from "../services/preconstruction";
import type { PreconstructionCopilotCitation, PreconstructionCopilotResponse } from "../types/api";
import { useBrowserVoiceCopilot } from "./useBrowserVoiceCopilot";

type Props = {
  projectId: string;
  projectLabel: string;
  planSetId?: string;
  planSetName?: string | null;
};

type CopilotMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  status?: PreconstructionCopilotResponse["status"];
  citations?: PreconstructionCopilotCitation[];
  suggestedPrompts?: string[];
};

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function buildWelcomeMessage(projectLabel: string, planSetName?: string | null): CopilotMessage {
  const scopeLabel = planSetName ? `plan set ${planSetName}` : projectLabel;
  return {
    id: createMessageId(),
    role: "assistant",
    status: "limited",
    content:
      `Ask about ${scopeLabel}: takeoff counts, sheet coverage, calibration, AI runs, snapshots, exports, and uploaded project documents. ` +
      "I will answer from live project data and the documents that have been parsed into this project.",
    suggestedPrompts: planSetName
      ? [
          "How many pending takeoff items are on this plan set?",
          "Which sheets in this plan set are calibrated?",
          "What is the latest snapshot status for this plan set?",
          "What was the last export created for this plan set?",
          "What do the uploaded project documents say about door hardware?",
        ]
      : [
          "List the plan sets for this project.",
          "How many takeoff items exist across this project?",
          "Which sheets are calibrated?",
          "What is the latest export created for this project?",
          "What do the uploaded project documents say about door hardware?",
        ],
  };
}

function statusLabel(status?: PreconstructionCopilotResponse["status"]): string {
  if (status === "needs_documents") return "Needs documents";
  if (status === "limited") return "Limited scope";
  return "Grounded";
}

export function PreconstructionCopilotPanel({ projectId, projectLabel, planSetId, planSetName }: Props) {
  const [messages, setMessages] = useState<CopilotMessage[]>(() => [buildWelcomeMessage(projectLabel, planSetName)]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = useState(false);
  const [pendingSpokenReply, setPendingSpokenReply] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const latestSuggestedPrompts = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.suggestedPrompts?.length) {
        return message.suggestedPrompts;
      }
    }
    return [];
  }, [messages]);

  const latestAssistantMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant") {
        return message;
      }
    }
    return null;
  }, [messages]);

  const submitQuestion = useCallback(async (promptOverride?: string) => {
    const prompt = (promptOverride ?? question).trim();
    if (!projectId || !prompt || loading) {
      return;
    }
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;

    const userMessage: CopilotMessage = {
      id: createMessageId(),
      role: "user",
      content: prompt,
    };

    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setError("");
    setLoading(true);

    try {
      const response = await queryPreconstructionCopilot({
        project: projectId,
        plan_set: planSetId ?? null,
        question: prompt,
      });
      if (requestId !== requestIdRef.current) return;
      const assistantMessage: CopilotMessage = {
        id: createMessageId(),
        role: "assistant",
        content: response.answer,
        status: response.status,
        citations: response.citations,
        suggestedPrompts: response.suggested_prompts,
      };
      setMessages((current) => [
        ...current,
        assistantMessage,
      ]);
      if (voiceRepliesEnabled) {
        setPendingSpokenReply(assistantMessage.content);
      }
    } catch (err) {
      if (requestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : "Failed to query estimator copilot.");
    } finally {
      if (requestId !== requestIdRef.current) return;
      setLoading(false);
    }
  }, [loading, planSetId, projectId, question, voiceRepliesEnabled]);

  const {
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
  } = useBrowserVoiceCopilot({
    onFinalTranscript: (transcript) => {
      setQuestion(transcript);
      void submitQuestion(transcript);
    },
    onInterimTranscript: (transcript) => {
      setQuestion(transcript);
    },
  });

  useEffect(() => {
    requestIdRef.current += 1;
    stopListening();
    stopSpeaking();
    clearVoiceError();
    setMessages([buildWelcomeMessage(projectLabel, planSetName)]);
    setQuestion("");
    setError("");
    setLoading(false);
    setVoiceRepliesEnabled(false);
    setPendingSpokenReply(null);
  }, [clearVoiceError, planSetId, planSetName, projectId, projectLabel, stopListening, stopSpeaking]);

  useEffect(() => {
    if (!voiceRepliesEnabled || !pendingSpokenReply) return;
    speakText(pendingSpokenReply);
    setPendingSpokenReply(null);
  }, [pendingSpokenReply, speakText, voiceRepliesEnabled]);

  return (
    <Card className="min-w-0">
      <CardHeader>
        <CardTitle>Estimator Copilot</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Grounded in live preconstruction data for {planSetName ? `plan set ${planSetName}` : projectLabel}.
        </p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <div className="max-h-[420px] space-y-3 overflow-y-auto pr-1" aria-live="polite">
          {messages.map((message) => (
            <div
              key={message.id}
              className={
                message.role === "assistant"
                  ? "rounded-lg border border-border bg-muted/50 p-3"
                  : "rounded-lg border border-primary/20 bg-primary/5 p-3"
              }
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {message.role === "assistant" ? "Copilot" : "You"}
                </span>
                {message.role === "assistant" && message.status ? (
                  <span className="text-[11px] text-muted-foreground">{statusLabel(message.status)}</span>
                ) : null}
              </div>
              <p className="mt-2 text-sm leading-6 text-foreground">{message.content}</p>
              {message.citations?.length ? (
                <ul className="mt-3 space-y-1 text-xs text-muted-foreground">
                  {message.citations.map((citation) => (
                    <li key={`${message.id}-${citation.kind}-${citation.id}`}>
                      <span className="font-medium text-foreground">{citation.label}</span>
                      {" - "}
                      {citation.detail}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
          {loading ? (
            <div className="rounded-lg border border-border bg-muted/50 p-3 text-sm text-muted-foreground">
              Checking live project data...
            </div>
          ) : null}
        </div>
        {latestSuggestedPrompts.length ? (
          <div className="flex flex-wrap gap-2">
            {latestSuggestedPrompts.map((prompt) => (
              <Button
                key={prompt}
                type="button"
                variant="outline"
                className="h-auto whitespace-normal px-3 py-2 text-left"
                onClick={() => void submitQuestion(prompt)}
                disabled={loading}
              >
                {prompt}
              </Button>
            ))}
          </div>
        ) : null}
        <div className="space-y-2 rounded-lg border border-border/70 bg-muted/40 p-3">
          <div className="flex flex-wrap items-center gap-2">
            <Button
              type="button"
              variant={isListening ? "secondary" : "outline"}
              onClick={() => {
                clearVoiceError();
                startListening();
              }}
              disabled={!recognitionSupported || loading || !projectId}
            >
              {isListening ? "Listening..." : "Start voice"}
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={stopListening}
              disabled={!isListening}
            >
              Stop
            </Button>
            <Button
              type="button"
              variant={voiceRepliesEnabled ? "default" : "outline"}
              onClick={() => setVoiceRepliesEnabled((current) => !current)}
              disabled={!speechOutputSupported}
            >
              {voiceRepliesEnabled ? "Spoken replies on" : "Spoken replies off"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => latestAssistantMessage && speakText(latestAssistantMessage.content)}
              disabled={!speechOutputSupported || !latestAssistantMessage}
            >
              Speak last answer
            </Button>
            <Button
              type="button"
              variant="ghost"
              onClick={stopSpeaking}
              disabled={!isSpeaking}
            >
              Stop speaking
            </Button>
          </div>
          {!recognitionSupported ? (
            <p className="text-xs text-muted-foreground">
              Voice input uses the browser speech-recognition API and is unavailable in this browser.
            </p>
          ) : null}
          {voiceError ? <p className="text-xs text-destructive">{voiceError}</p> : null}
          {isListening || interimTranscript ? (
            <p className="text-xs text-muted-foreground">
              {interimTranscript ? `Hearing: ${interimTranscript}` : "Listening for a command..."}
            </p>
          ) : null}
        </div>
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(event) => {
            event.preventDefault();
            void submitQuestion();
          }}
        >
          <Input
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask about takeoff, sheets, AI runs, snapshots, or exports"
            aria-label="Ask estimator copilot"
            disabled={loading || !projectId}
            className="flex-1"
          />
          <Button type="submit" disabled={loading || !projectId || !question.trim()}>
            Ask
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
