#!/usr/bin/env node
/**
 * Session logger hook for subagents. Runs on the SubagentStop event.
 *
 * Parallel to stop-log.cjs but reads subagent-specific fields. Exits 0 always.
 */

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const TZ = process.env.TZ || "__TZ__";

function main() {
  let hookInput;
  try {
    const raw = fs.readFileSync(0, "utf-8");
    hookInput = JSON.parse(raw);
  } catch {
    return;
  }

  const transcriptPath = hookInput.agent_transcript_path || "";
  const sessionId = hookInput.session_id || "unknown";
  const agentId = hookInput.agent_id || "unknown";
  const agentType = hookInput.agent_type || "subagent";

  if (!transcriptPath || !fs.existsSync(transcriptPath)) return;

  // Wait for transcript to finish flushing (file size stabilizes)
  let prevSize = -1;
  for (let i = 0; i < 10; i++) {
    let currSize = 0;
    try {
      currSize = fs.statSync(transcriptPath).size;
    } catch {}
    if (currSize === prevSize) break;
    prevSize = currSize;
    execFileSync("sleep", ["0.2"]);
  }

  // Extract start timestamp from first record that has one
  let startTs = null;
  try {
    const content = fs.readFileSync(transcriptPath, "utf-8");
    for (const line of content.split("\n")) {
      if (!line.trim()) continue;
      try {
        const ts = JSON.parse(line).timestamp;
        if (ts) {
          startTs = ts;
          break;
        }
      } catch {
        continue;
      }
    }
  } catch {}

  // Convert UTC timestamp to local time
  let dateStr, timePart, localTs;
  if (startTs) {
    try {
      const utcDate = new Date(startTs);
      const formatter = new Intl.DateTimeFormat("en-CA", {
        timeZone: TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
      });
      dateStr = formatter.format(utcDate);

      const timeFmt = new Intl.DateTimeFormat("en-GB", {
        timeZone: TZ,
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      timePart = timeFmt.format(utcDate).replace(":", "");

      const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: TZ,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      }).formatToParts(utcDate);
      const p = {};
      for (const { type, value } of parts) p[type] = value;
      localTs = `${p.year}-${p.month}-${p.day}T${p.hour}:${p.minute}:${p.second}`;
    } catch {
      dateStr = new Date().toISOString().slice(0, 10);
      timePart = "0000";
      localTs = startTs || "";
    }
  } else {
    dateStr = new Date().toISOString().slice(0, 10);
    timePart = "0000";
    localTs = "";
  }

  const logsDir = path.join(__dirname, "..", "logs");
  fs.mkdirSync(logsDir, { recursive: true });

  const shortSession = sessionId.slice(0, 8);
  const shortAgent = agentId.slice(0, 8);
  const logFile = path.join(logsDir, `${dateStr}-${timePart}-${shortSession}-subagent-${agentType}-${shortAgent}.md`);
  const errorLog = path.join(logsDir, ".converter-errors.log");

  try {
    execFileSync(process.execPath, [
      path.join(__dirname, "log-converter.cjs"),
      "--transcript", transcriptPath,
      "--output", logFile,
      "--session-id", sessionId,
      "--date", dateStr,
      "--start-time", localTs,
      "--agent-type", agentType,
      "--agent-id", agentId,
    ], {
      stdio: ["pipe", "pipe", fs.openSync(errorLog, "a")],
    });
  } catch {}

  // Remove error log if empty — its presence is the signal
  try {
    if (fs.existsSync(errorLog) && fs.statSync(errorLog).size === 0) {
      fs.unlinkSync(errorLog);
    }
  } catch {}
}

try {
  main();
} catch {}
process.exit(0);
