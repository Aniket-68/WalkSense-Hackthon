const PIPELINE_NODES = [
  { key: "camera", label: "Camera", icon: "📷" },
  { key: "yolo", label: "YOLO", icon: "🔍" },
  { key: "safety", label: "Safety", icon: "🛡️" },
  { key: "vlm", label: "VLM", icon: "👁️" },
  { key: "llm", label: "LLM", icon: "🧠" },
  { key: "tts", label: "TTS", icon: "🔊" },
];

function getNodeStatus(pipelineData, key) {
  const node = pipelineData?.[key];
  if (!node) return "idle";
  if (node.is_processing) return "processing";
  if (node.active) return "active";
  return "idle";
}

function getLatency(pipelineData, key) {
  const node = pipelineData?.[key];
  if (!node?.last_latency_ms) return null;
  const ms = node.last_latency_ms;
  if (ms > 1000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.round(ms)}ms`;
}

function getExtra(pipelineData, key) {
  const node = pipelineData?.[key];
  if (key === "yolo" && node?.detections_count > 0) {
    return `${node.detections_count} obj`;
  }
  if (key === "safety" && node?.last_alert) {
    return "⚠ Alert";
  }
  return null;
}

export default function PipelineMonitor({ state }) {
  const pipeline = state?.pipeline || {};
  const isRunning = state?.system_status === "RUNNING";
  const isStarting = state?.system_status === "STARTING";

  return (
    <div className="pipeline-container">
      {/* Initializing banner */}
      {isStarting && (
        <div className="pipeline-init-banner">
          <svg
            className="spin-icon"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
          >
            <path d="M12 2a10 10 0 0 1 10 10" />
          </svg>
          <span>
            Loading models &amp; camera — this may take a few seconds…
          </span>
        </div>
      )}
      <div className="pipeline-row">
        {PIPELINE_NODES.map((node, i) => {
          const status = isRunning
            ? getNodeStatus(pipeline, node.key)
            : isStarting
              ? "loading"
              : "idle";
          const latency = getLatency(pipeline, node.key);
          const extra = getExtra(pipeline, node.key);

          // Determine if arrow before this node should be active
          const prevActive =
            i > 0 &&
            isRunning &&
            (getNodeStatus(pipeline, PIPELINE_NODES[i - 1].key) !== "idle" ||
              status !== "idle");

          return (
            <div
              key={node.key}
              style={{ display: "flex", alignItems: "center" }}
            >
              {/* Arrow connector */}
              {i > 0 && (
                <div
                  className={`pipeline-arrow ${prevActive ? "active" : ""}`}
                />
              )}

              {/* Node */}
              <div className={`pipeline-node ${status}`}>
                <div className="pipeline-node-icon">
                  {node.icon}
                  {status === "processing" && (
                    <span
                      style={{
                        position: "absolute",
                        inset: -4,
                        borderRadius: "50%",
                        border: "2px solid var(--accent-cyan)",
                        animation: "pulse-ring 1.5s ease-out infinite",
                        pointerEvents: "none",
                      }}
                    />
                  )}
                </div>
                <span className="pipeline-node-label">{node.label}</span>
                <span className="pipeline-node-latency">
                  {latency || extra || "\u00A0"}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
