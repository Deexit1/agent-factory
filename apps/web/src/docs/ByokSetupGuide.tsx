interface ByokSetupGuideProps {
  provider: "anthropic" | "openai";
}

const GUIDES: Record<ByokSetupGuideProps["provider"], { title: string; steps: string[] }> = {
  anthropic: {
    title: "Anthropic (Claude)",
    steps: [
      "Sign in at console.anthropic.com.",
      "Go to Settings → API Keys and click \"Create Key\".",
      "Copy the key (it starts with sk-ant-) — you won't be able to see it again.",
      "Paste it into the \"Add key\" field on the Keys page here and select Anthropic.",
    ],
  },
  openai: {
    title: "OpenAI",
    steps: [
      "Sign in at platform.openai.com.",
      "Go to API keys and click \"Create new secret key\".",
      "Copy the key (it starts with sk-) — you won't be able to see it again.",
      "Paste it into the \"Add key\" field on the Keys page here and select OpenAI.",
    ],
  },
};

export function ByokSetupGuide({ provider }: ByokSetupGuideProps): React.JSX.Element {
  const guide = GUIDES[provider];
  return (
    <div className="rounded border border-gray-200 p-4 text-sm">
      <h3 className="font-semibold text-gray-900">Getting a {guide.title} API key</h3>
      <ol className="mt-2 list-decimal space-y-1 pl-5 text-gray-600">
        {guide.steps.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ol>
      <p className="mt-2 text-xs text-gray-500">
        Your key is written straight to our secrets store and never stored in our database,
        logs, or event history — only the last 4 characters are shown here for identification.
      </p>
    </div>
  );
}
