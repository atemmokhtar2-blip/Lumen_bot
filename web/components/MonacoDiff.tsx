"use client";

import { DiffEditor } from "@monaco-editor/react";

function langFromPath(path: string): string {
  const p = path.toLowerCase();
  if (p.endsWith(".py")) return "python";
  if (p.endsWith(".ts") || p.endsWith(".tsx")) return "typescript";
  if (p.endsWith(".js") || p.endsWith(".jsx")) return "javascript";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".md")) return "markdown";
  return "plaintext";
}

/** Side-by-side diff using official Monaco DiffEditor. */
export function MonacoDiff({
  path,
  original,
  modified,
  height = "520px",
}: {
  path: string;
  original: string;
  modified: string;
  height?: string;
}) {
  return (
    <DiffEditor
      height={height}
      language={langFromPath(path)}
      original={original}
      modified={modified}
      theme="vs-dark"
      options={{
        readOnly: true,
        renderSideBySide: true,
        minimap: { enabled: false },
        fontSize: 13,
        automaticLayout: true,
      }}
    />
  );
}
