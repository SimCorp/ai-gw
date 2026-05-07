import * as React from "react";

export interface CodeBlockProps {
  code: string;
  language?: string;
  copyable?: boolean;
}

export function CodeBlock({ code, language, copyable = false }: CodeBlockProps) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      const timer = setTimeout(() => setCopied(false), 2000);
      return () => clearTimeout(timer);
    } catch {
      // clipboard not available
    }
  }, [code]);

  return (
    <div className="code-block" data-language={language}>
      {copyable && (
        <button
          type="button"
          className="copy"
          onClick={handleCopy}
          aria-label="Copy code"
        >
          {copied ? "Copied!" : "Copy"}
        </button>
      )}
      <code>{code}</code>
    </div>
  );
}
