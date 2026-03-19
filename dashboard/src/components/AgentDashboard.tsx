// dashboard/src/components/AgentDashboard.tsx
// Full pipeline dashboard — start builds, watch progress, view outputs

import { useState, useEffect, useRef, useCallback } from "react";

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

type AgentStatus = "idle" | "running" | "done" | "error";

interface AgentInfo {
  name: string;
  label: string;
  role: string;
  description: string;
}

interface AgentResult {
  output: string;
  cost_usd: number;
  duration_seconds: number;
  tool_calls: { tool: string; input: unknown }[];
  errors: string[];
}

interface Job {
  job_id: string;
  status: "pending" | "running" | "done" | "failed" | "aborted";
  results?: Record<string, AgentResult>;
  summary?: string;
  error?: string;
}

// ── Agent registry ────────────────────────────────────────────────────────────

const ALL_AGENTS: AgentInfo[] = [
  { name: "pm",           label: "PM",           role: "Product Manager",    description: "PRDs & user stories" },
  { name: "ui_ux",        label: "UI/UX",        role: "Product Designer",   description: "Wireframes & specs" },
  { name: "frontend",     label: "Frontend",     role: "Frontend Engineer",  description: "React/TypeScript" },
  { name: "mobile",       label: "Mobile",       role: "Mobile Engineer",    description: "React Native/Expo" },
  { name: "backend",      label: "Backend",      role: "Backend Engineer",   description: "FastAPI & PostgreSQL" },
  { name: "security",     label: "Security",     role: "Security Engineer",  description: "OWASP & SAST audit" },
  { name: "code_review",  label: "Review",       role: "Principal Engineer", description: "Code quality" },
  { name: "qa",           label: "QA",           role: "QA Engineer",        description: "Test suite" },
  { name: "devops",       label: "DevOps",       role: "DevOps Engineer",    description: "Docker & CI/CD" },
  { name: "monetisation", label: "Monetisation", role: "Growth Engineer",    description: "Stripe & pricing" },
];

const STATUS_DOT: Record<AgentStatus, string> = {
  idle:    "bg-gray-300",
  running: "bg-amber-400 animate-pulse",
  done:    "bg-emerald-500",
  error:   "bg-red-500",
};

// ── Main component ────────────────────────────────────────────────────────────

export default function AgentDashboard() {
  const [feature, setFeature] = useState("");
  const [projectId, setProjectId] = useState("my-project");
  const [selectedAgents, setSelectedAgents] = useState<string[]>(
    ["pm", "ui_ux", "frontend", "backend", "security", "code_review", "qa", "devops"]
  );
  const [job, setJob] = useState<Job | null>(null);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});
  const [selectedOutput, setSelectedOutput] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval>>();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Pipeline control ────────────────────────────────────────────────────────

  async function startPipeline() {
    if (!feature.trim() || !selectedAgents.length) return;

    // Reset state
    setJob(null);
    setSelectedOutput(null);
    const initStatuses: Record<string, AgentStatus> = {};
    selectedAgents.forEach(a => initStatuses[a] = "idle");
    setAgentStatuses(initStatuses);

    const res = await fetch(`${API}/api/pipeline/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ description: feature, project_id: projectId, agents: selectedAgents }),
    });
    const data: Job = await res.json();
    setJob(data);
  }

  // ── Polling ─────────────────────────────────────────────────────────────────

  const pollJob = useCallback(async (jobId: string) => {
    const res = await fetch(`${API}/api/pipeline/jobs/${jobId}`);
    const data: Job = await res.json();
    setJob(data);

    if (data.results) {
      const statuses: Record<string, AgentStatus> = {};
      selectedAgents.forEach(name => {
        statuses[name] = data.results![name]
          ? (data.results![name].errors.length ? "error" : "done")
          : (data.status === "running" ? "running" : "idle");
      });
      setAgentStatuses(statuses);
    }

    if (["done", "failed", "aborted"].includes(data.status)) {
      clearInterval(pollRef.current);
    }
  }, [selectedAgents]);

  useEffect(() => {
    if (!job?.job_id || ["done", "failed", "aborted"].includes(job.status)) return;
    pollRef.current = setInterval(() => pollJob(job.job_id), 2500);
    return () => clearInterval(pollRef.current);
  }, [job?.job_id, pollJob]);

  // ── Security audit shortcut ──────────────────────────────────────────────────

  async function runSecurityAudit() {
    const code = textareaRef.current?.value;
    if (!code?.trim()) return alert("Paste your code first");
    const res = await fetch(`${API}/api/agents/security/audit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: { "pasted_code.py": code }, project_id: projectId }),
    });
    const result = await res.json();
    setSelectedOutput(result.output ?? JSON.stringify(result, null, 2));
  }

  // ── Derived state ───────────────────────────────────────────────────────────

  const doneCount  = Object.values(agentStatuses).filter(s => s === "done").length;
  const totalCost  = job?.results
    ? Object.values(job.results).reduce((s, r) => s + r.cost_usd, 0)
    : 0;
  const isRunning  = job?.status === "pending" || job?.status === "running";
  const isDone     = job?.status === "done";

  // ── Render ──────────────────────────────────────────────────────────────────

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950 p-6 font-sans">
      <div className="max-w-5xl mx-auto space-y-6">

        {/* Header */}
        <div>
          <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
            AI Agent Org
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            One-person enterprise engineering team
          </p>
        </div>

        {/* Input card */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200
                        dark:border-gray-800 p-5 space-y-4">
          <div className="flex gap-3">
            <input
              value={feature}
              onChange={e => setFeature(e.target.value)}
              placeholder="Describe the feature or product to build..."
              className="flex-1 rounded-xl border border-gray-300 dark:border-gray-700
                         bg-transparent px-4 py-2.5 text-sm text-gray-900 dark:text-white
                         placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
              onKeyDown={e => e.key === "Enter" && !e.shiftKey && startPipeline()}
            />
            <input
              value={projectId}
              onChange={e => setProjectId(e.target.value)}
              placeholder="project-id"
              className="w-36 rounded-xl border border-gray-300 dark:border-gray-700
                         bg-transparent px-4 py-2.5 text-sm text-gray-500 dark:text-gray-400
                         focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* Agent selector */}
          <div className="flex flex-wrap gap-2">
            {ALL_AGENTS.map(a => {
              const active = selectedAgents.includes(a.name);
              return (
                <button
                  key={a.name}
                  onClick={() => setSelectedAgents(prev =>
                    active ? prev.filter(n => n !== a.name) : [...prev, a.name]
                  )}
                  className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors
                    ${active
                      ? "bg-blue-600 border-blue-600 text-white"
                      : "bg-transparent border-gray-300 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:border-blue-400"
                    }`}
                >
                  {a.label}
                </button>
              );
            })}
          </div>

          <div className="flex gap-3">
            <button
              onClick={startPipeline}
              disabled={isRunning || !feature.trim() || !selectedAgents.length}
              className="flex-1 rounded-xl bg-blue-600 text-white text-sm font-medium
                         py-2.5 hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed
                         transition-colors"
            >
              {isRunning ? "Running pipeline..." : "Run pipeline"}
            </button>
            <button
              onClick={runSecurityAudit}
              className="rounded-xl border border-gray-300 dark:border-gray-700 text-sm
                         font-medium px-4 py-2.5 hover:bg-gray-50 dark:hover:bg-gray-800
                         text-gray-700 dark:text-gray-300 transition-colors"
            >
              Security audit
            </button>
          </div>
        </div>

        {/* Code input for security audit */}
        <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200
                        dark:border-gray-800 p-5">
          <p className="text-xs text-gray-500 mb-2 font-medium">
            Paste code for security audit (optional)
          </p>
          <textarea
            ref={textareaRef}
            rows={5}
            placeholder="Paste Python, JavaScript, or any code here for a direct security scan..."
            className="w-full rounded-xl border border-gray-200 dark:border-gray-700
                       bg-gray-50 dark:bg-gray-800 px-4 py-3 text-sm font-mono
                       text-gray-800 dark:text-gray-200 placeholder-gray-400
                       focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
          />
        </div>

        {/* Progress */}
        {job && (
          <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200
                          dark:border-gray-800 p-5">
            <div className="flex justify-between items-center mb-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-gray-900 dark:text-white">
                  {job.status === "running" ? "Running" : job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                </span>
                <span className="text-xs text-gray-400">
                  {doneCount}/{selectedAgents.length} agents
                </span>
              </div>
              <div className="flex items-center gap-4 text-xs text-gray-500">
                {isDone && <span>Total cost: ${totalCost.toFixed(4)}</span>}
                <span className="font-mono">{job.job_id.slice(0, 8)}</span>
              </div>
            </div>

            {/* Progress bar */}
            <div className="h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden mb-5">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-500"
                style={{ width: `${selectedAgents.length ? (doneCount / selectedAgents.length) * 100 : 0}%` }}
              />
            </div>

            {/* Agent grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
              {selectedAgents.map(name => {
                const info = ALL_AGENTS.find(a => a.name === name)!;
                const status = agentStatuses[name] ?? "idle";
                const result = job.results?.[name];

                return (
                  <button
                    key={name}
                    onClick={() => result && setSelectedOutput(
                      selectedOutput === name ? null : name
                    )}
                    className={`rounded-xl p-3 text-left border transition-all
                      ${selectedOutput === name
                        ? "border-blue-500 bg-blue-50 dark:bg-blue-950"
                        : "border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-800/50 hover:border-gray-300"
                      } ${result ? "cursor-pointer" : "cursor-default"}`}
                  >
                    <div className="flex items-start justify-between gap-1 mb-1.5">
                      <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                        {info.label}
                      </span>
                      <span className={`w-2 h-2 rounded-full mt-0.5 flex-shrink-0 ${STATUS_DOT[status]}`} />
                    </div>
                    <div className="text-xs text-gray-400">{info.description}</div>
                    {result && (
                      <div className="text-xs text-gray-400 mt-1.5">
                        {result.duration_seconds.toFixed(0)}s · ${result.cost_usd.toFixed(4)}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Output panel */}
        {(selectedOutput !== null) && (() => {
          const content = typeof selectedOutput === "string" && job?.results?.[selectedOutput]
            ? job.results[selectedOutput].output
            : (typeof selectedOutput === "string" ? selectedOutput : "");

          const agentInfo = typeof selectedOutput === "string"
            ? ALL_AGENTS.find(a => a.name === selectedOutput)
            : null;

          return (
            <div className="bg-white dark:bg-gray-900 rounded-2xl border border-gray-200
                            dark:border-gray-800 overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3
                              border-b border-gray-100 dark:border-gray-800">
                <div>
                  <span className="text-sm font-medium text-gray-900 dark:text-white">
                    {agentInfo?.role ?? "Output"}
                  </span>
                  {agentInfo && (
                    <span className="text-xs text-gray-400 ml-2">{agentInfo.description}</span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => navigator.clipboard.writeText(content)}
                    className="text-xs text-gray-500 hover:text-gray-700 px-3 py-1.5
                               rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Copy
                  </button>
                  <button
                    onClick={() => setSelectedOutput(null)}
                    className="text-xs text-gray-400 hover:text-gray-600 px-2 py-1.5
                               rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800"
                  >
                    ✕
                  </button>
                </div>
              </div>
              <pre className="p-5 text-xs leading-relaxed font-mono
                              text-gray-800 dark:text-gray-200
                              max-h-[520px] overflow-y-auto whitespace-pre-wrap">
                {content}
              </pre>
            </div>
          );
        })()}

        {/* Summary */}
        {job?.summary && isDone && (
          <div className="bg-emerald-50 dark:bg-emerald-950 rounded-2xl border
                          border-emerald-200 dark:border-emerald-800 p-5">
            <p className="text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-2">
              Pipeline complete
            </p>
            <pre className="text-xs text-emerald-800 dark:text-emerald-200 font-mono whitespace-pre-wrap">
              {job.summary}
            </pre>
          </div>
        )}

        {/* Error */}
        {job?.error && (
          <div className="bg-red-50 dark:bg-red-950 rounded-2xl border
                          border-red-200 dark:border-red-800 p-5">
            <p className="text-xs font-medium text-red-700 dark:text-red-300 mb-1">Error</p>
            <p className="text-xs text-red-600 dark:text-red-400 font-mono">{job.error}</p>
          </div>
        )}
      </div>
    </div>
  );
}
