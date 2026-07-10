import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

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
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Getting a {guide.title} API key</CardTitle>
      </CardHeader>
      <CardContent>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-muted-foreground">
          {guide.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-muted-foreground">
          Your key is written straight to our secrets store and never stored in our database,
          logs, or event history — only the last 4 characters are shown here for identification.
        </p>
      </CardContent>
    </Card>
  );
}
