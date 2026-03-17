import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { queryPreconstructionCopilot } from "../services/preconstruction";
import type { PreconstructionCopilotCitation, PreconstructionCopilotResponse } from "../types/api";
import { useBrowserVoiceCopilot } from "./useBrowserVoiceCopilot";

type AnalysisProvider = "mock" | "openai_vision" | "cad_dxf";
type AssemblyProfile = "auto" | "none" | "door_set" | "window_set" | "fixture_set";

type CopilotMessage = {
  id: string;
  role: "assistant" | "user";
  content: string;
  status?: PreconstructionCopilotResponse["status"];
  citations?: PreconstructionCopilotCitation[];
};

type Props = {
  projectId: string;
  planSetId: string;
  sheetId: string;
  sheetLabel: string;
  selectedAnnotationId?: string | null;
  selectedAnnotationLabel?: string | null;
  analysisProvider: AnalysisProvider;
  onRunAnalysis: (prompt: string, provider: AnalysisProvider) => Promise<void>;
  onBatchAccept: () => Promise<void>;
  onCreateTakeoffFromAnnotation: (annotationId: string, assemblyProfile: AssemblyProfile) => Promise<void>;
  onCreateSnapshot: (name: string) => Promise<void>;
  onExport: (exportType: "json" | "csv") => Promise<void>;
};

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

function statusLabel(status?: PreconstructionCopilotResponse["status"]): string {
  if (status === "needs_documents") return "Needs documents";
  if (status === "limited") return "Limited";
  return "Grounded";
}

function buildWelcomeMessage(sheetLabel: string): CopilotMessage {
  return {
    id: createMessageId(),
    role: "assistant",
    status: "limited",
    content:
      `Ask me to run analysis on ${sheetLabel}, accept high-confidence suggestions, create a takeoff package from the selected annotation, create a snapshot, or export this plan set.`,
  };
}

export function SheetCopilotPanel({
  projectId,
  planSetId,
  sheetId,
  sheetLabel,
  selectedAnnotationId,
  selectedAnnotationLabel,
  analysisProvider,
  onRunAnalysis,
  onBatchAccept,
  onCreateTakeoffFromAnnotation,
  onCreateSnapshot,
  onExport,
}: Props) {
  const [messages, setMessages] = useState<CopilotMessage[]>(() => [buildWelcomeMessage(sheetLabel)]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [voiceRepliesEnabled, setVoiceRepliesEnabled] = useState(false);
  const [pendingSpokenReply, setPendingSpokenReply] = useState<string | null>(null);
  const requestIdRef = useRef(0);

  const quickPrompts = useMemo(
    () => [
      `Find all doors on ${sheetLabel}`,
      "Accept all high-confidence suggestions",
      selectedAnnotationId ? "Create takeoff package from this annotation" : "Create takeoff package from the selected annotation",
      "Create snapshot for this plan set",
      "Export CSV for this plan set",
    ],
    [selectedAnnotationId, sheetLabel]
  );

  const latestAssistantMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant") {
        return message;
      }
    }
    return null;
  }, [messages]);

  const executeActionPlan = async (actionPlan: NonNullable<PreconstructionCopilotResponse["action_plan"]>) => {
    switch (actionPlan.kind) {
      case "run_analysis":
        await onRunAnalysis(actionPlan.prompt ?? question, (actionPlan.provider_name as AnalysisProvider) || analysisProvider);
        return actionPlan.label;
      case "batch_accept_suggestions":
        await onBatchAccept();
        return actionPlan.label;
      case "create_takeoff_from_annotation":
        if (!actionPlan.annotation_id) throw new Error("No annotation selected for takeoff creation.");
        await onCreateTakeoffFromAnnotation(
          actionPlan.annotation_id,
          (actionPlan.assembly_profile as AssemblyProfile) || "auto"
        );
        return actionPlan.label;
      case "create_snapshot":
        await onCreateSnapshot(actionPlan.snapshot_name ?? `Copilot Snapshot ${new Date().toISOString().slice(0, 16)}`);
        return actionPlan.label;
      case "export_plan_set":
        await onExport((actionPlan.export_type as "json" | "csv") || "json");
        return actionPlan.label;
      default:
        throw new Error(`Unsupported copilot action '${actionPlan.kind}'.`);
    }
  };

  const submitQuestion = useCallback(async (promptOverride?: string) => {
    const prompt = (promptOverride ?? question).trim();
    if (!prompt || loading) return;
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
        plan_set: planSetId,
        plan_sheet: sheetId,
        annotation: selectedAnnotationId ?? null,
        provider_name: analysisProvider,
        question: prompt,
      });
      if (requestId !== requestIdRef.current) return;

      let content = response.answer;
      if (response.action_plan) {
        const actionLabel = await executeActionPlan(response.action_plan);
        content = `${response.answer} Executed: ${actionLabel}.`;
      }
      const assistantMessage: CopilotMessage = {
        id: createMessageId(),
        role: "assistant",
        content,
        status: response.status,
        citations: response.citations,
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
      setError(err instanceof Error ? err.message : "Failed to run sheet copilot command.");
    } finally {
      if (requestId !== requestIdRef.current) return;
      setLoading(false);
    }
  }, [
    analysisProvider,
    executeActionPlan,
    loading,
    planSetId,
    projectId,
    question,
    selectedAnnotationId,
    sheetId,
    voiceRepliesEnabled,
  ]);

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
    setMessages([buildWelcomeMessage(sheetLabel)]);
    setVoiceRepliesEnabled(false);
    setPendingSpokenReply(null);
    setQuestion("");
    setError("");
    setLoading(false);
  }, [clearVoiceError, planSetId, projectId, sheetId, sheetLabel, stopListening, stopSpeaking]);

  useEffect(() => {
    if (!voiceRepliesEnabled || !pendingSpokenReply) return;
    speakText(pendingSpokenReply);
    setPendingSpokenReply(null);
  }, [pendingSpokenReply, speakText, voiceRepliesEnabled]);

  return (
    <div className="card" style={{ flex: "1" }}>
      <h4>Sheet copilot</h4>
      <p className="empty-hint">
        Scoped to {sheetLabel}. {selectedAnnotationId ? `Selected annotation: ${selectedAnnotationLabel || "current annotation"}.` : "Select an annotation to let me create a takeoff package."}
      </p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginBottom: "0.75rem" }}>
        {quickPrompts.map((prompt) => (
          <button key={prompt} type="button" onClick={() => void submitQuestion(prompt)} disabled={loading}>
            {prompt}
          </button>
        ))}
      </div>
      <div className="card" style={{ marginBottom: "0.75rem", padding: "0.75rem", background: "#f8fafc" }}>
        <div className="row" style={{ gap: "0.5rem", flexWrap: "wrap", marginBottom: "0.5rem" }}>
          <button
            type="button"
            onClick={() => {
              clearVoiceError();
              startListening();
            }}
            disabled={!recognitionSupported || loading}
          >
            {isListening ? "Listening..." : "Start voice"}
          </button>
          <button type="button" onClick={stopListening} disabled={!isListening}>
            Stop
          </button>
          <button
            type="button"
            onClick={() => setVoiceRepliesEnabled((current) => !current)}
            disabled={!speechOutputSupported}
          >
            {voiceRepliesEnabled ? "Spoken replies on" : "Spoken replies off"}
          </button>
          <button
            type="button"
            onClick={() => latestAssistantMessage && speakText(latestAssistantMessage.content)}
            disabled={!speechOutputSupported || !latestAssistantMessage}
          >
            Speak last answer
          </button>
          <button type="button" onClick={stopSpeaking} disabled={!isSpeaking}>
            Stop speaking
          </button>
        </div>
        {!recognitionSupported ? (
          <p className="empty-hint" style={{ marginBottom: "0.25rem" }}>
            Voice input uses the browser speech-recognition API and is unavailable in this browser.
          </p>
        ) : null}
        {voiceError ? <p className="error">{voiceError}</p> : null}
        {isListening || interimTranscript ? (
          <p className="empty-hint" style={{ marginBottom: 0 }}>
            {interimTranscript ? `Hearing: ${interimTranscript}` : "Listening for a command..."}
          </p>
        ) : null}
      </div>
      {error ? <p className="error">{error}</p> : null}
      <div style={{ maxHeight: "260px", overflowY: "auto", marginBottom: "0.75rem" }} aria-live="polite">
        {messages.map((message) => (
          <div
            key={message.id}
            className="card"
            style={{
              marginBottom: "0.5rem",
              padding: "0.75rem",
              background: message.role === "assistant" ? "#f8fafc" : "#eef2ff",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", gap: "0.5rem" }}>
              <strong>{message.role === "assistant" ? "Copilot" : "You"}</strong>
              {message.role === "assistant" && message.status ? (
                <span className="empty-hint">{statusLabel(message.status)}</span>
              ) : null}
            </div>
            <p style={{ marginBottom: message.citations?.length ? "0.5rem" : 0 }}>{message.content}</p>
            {message.citations?.length ? (
              <ul style={{ margin: 0, paddingLeft: "1rem" }}>
                {message.citations.map((citation) => (
                  <li key={`${message.id}-${citation.kind}-${citation.id}`} className="empty-hint">
                    <strong>{citation.label}</strong>: {citation.detail}
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
        {loading ? <p className="empty-hint">Working...</p> : null}
      </div>
      <form
        className="row"
        onSubmit={(event) => {
          event.preventDefault();
          void submitQuestion();
        }}
      >
        <input
          type="text"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask me to act on this sheet"
          aria-label="Ask sheet copilot"
          style={{ flex: 1, minWidth: "12rem" }}
          disabled={loading}
        />
        <button type="submit" disabled={loading || !question.trim()}>
          Run
        </button>
      </form>
    </div>
  );
}
