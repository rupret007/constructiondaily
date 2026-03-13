import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { queryPreconstructionCopilot } from "../services/preconstruction";
import type { PreconstructionCopilotCitation, PreconstructionCopilotResponse } from "../types/api";

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
      `Ask about ${scopeLabel}: takeoff counts, sheet coverage, calibration, AI runs, snapshots, and exports. ` +
      "I will answer from live project data and call out when a question needs specs or other documents we do not ingest yet.",
    suggestedPrompts: planSetName
      ? [
          "How many pending takeoff items are on this plan set?",
          "Which sheets in this plan set are calibrated?",
          "What is the latest snapshot status for this plan set?",
          "What was the last export created for this plan set?",
        ]
      : [
          "List the plan sets for this project.",
          "How many takeoff items exist across this project?",
          "Which sheets are calibrated?",
          "What is the latest export created for this project?",
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

  useEffect(() => {
    setMessages([buildWelcomeMessage(projectLabel, planSetName)]);
    setQuestion("");
    setError("");
    setLoading(false);
  }, [projectId, projectLabel, planSetId, planSetName]);

  const latestSuggestedPrompts = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.suggestedPrompts?.length) {
        return message.suggestedPrompts;
      }
    }
    return [];
  }, [messages]);

  const submitQuestion = async (promptOverride?: string) => {
    const prompt = (promptOverride ?? question).trim();
    if (!projectId || !prompt || loading) {
      return;
    }

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
      setMessages((current) => [
        ...current,
        {
          id: createMessageId(),
          role: "assistant",
          content: response.answer,
          status: response.status,
          citations: response.citations,
          suggestedPrompts: response.suggested_prompts,
        },
      ]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to query estimator copilot.");
    } finally {
      setLoading(false);
    }
  };

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
