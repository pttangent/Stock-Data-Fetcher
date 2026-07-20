import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const forwarded = process.argv.slice(2);
if (forwarded[0] === "--") forwarded.shift();

const parser = resolve(dirname(fileURLToPath(import.meta.url)), "../../tools/sec_pipeline/sec_pipeline.py");
const configured = process.env.SEC_PYTHON?.trim();
const candidates = configured ? [configured] : ["python", "python3"];

for (const command of candidates) {
  const result = spawnSync(command, [parser, ...forwarded], { stdio: "inherit" });
  if (result.error) {
    const code = (result.error as NodeJS.ErrnoException).code;
    if (code === "ENOENT" && !configured) continue;
    throw result.error;
  }
  if (result.signal) {
    console.error(`SEC parser terminated by signal ${result.signal}`);
    process.exitCode = 1;
  } else {
    process.exitCode = result.status ?? 1;
  }
  break;
}

if (process.exitCode === undefined) {
  console.error("Python was not found. Install Python 3.11+ or set SEC_PYTHON to the interpreter path.");
  process.exitCode = 1;
}
