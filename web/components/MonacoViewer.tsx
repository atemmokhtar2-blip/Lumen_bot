"use client";

import Editor from "@monaco-editor/react";

function langFromPath(path: string): string {
  const p = path.toLowerCase();
  if (p.endsWith(".py")) return "python";
  if (p.endsWith(".ts") || p.endsWith(".tsx")) return "typescript";
  if (p.endsWith(".js") || p.endsWith(".jsx")) return "javascript";
  if (p.endsWith(".json")) return "json";
  if (p.endsWith(".md")) return "markdown";
  if (p.endsWith(".yml") || p.endsWith(".yaml")) return "yaml";
  if (p.endsWith(".html")) return "html";
  if (p.endsWith(".css")) return "css";
  if (p.endsWith(".toml")) return "ini";
  if (p.endsWith(".sh")) return "shell";
  return "plaintext";
}

export function MonacoViewer({
  path,
  content,
  height = "520px",
}: {
  path: string;
  content: string;
  height?: string;
}) {
  return (
    <Editor
      height={height}
      language={langFromPath(path)}
      value={content}
      theme="vs-dark"
      options={{
        readOnly: true,
        minimap: { enabled: true },
        fontSize: 13,
        lineNumbers: "on",
        scrollBeyondLastLine: false,
        wordWrap: "on",
        automaticLayout: true,
      }}
    />
  );
}
