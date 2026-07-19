"use client";

import { useEffect } from "react";

const SWAGGER_UI_VERSION = "5.18.2";

type SwaggerUiBundle = {
  (config: Record<string, unknown>): void;
  presets: { apis: unknown };
  SwaggerUIStandalonePreset: unknown;
};

declare global {
  interface Window {
    SwaggerUIBundle?: SwaggerUiBundle;
  }
}

export default function ApiDocsPage() {
  useEffect(() => {
    const stylesheet = document.createElement("link");
    stylesheet.rel = "stylesheet";
    stylesheet.href = `https://unpkg.com/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui.css`;
    document.head.appendChild(stylesheet);

    const script = document.createElement("script");
    script.src = `https://unpkg.com/swagger-ui-dist@${SWAGGER_UI_VERSION}/swagger-ui-bundle.js`;
    script.async = true;
    script.onload = () => {
      const bundle = window.SwaggerUIBundle;
      if (!bundle) return;

      bundle({
        url: "/api/openapi",
        dom_id: "#swagger-ui",
        deepLinking: true,
        presets: [bundle.presets.apis, bundle.SwaggerUIStandalonePreset],
        layout: "StandaloneLayout",
      });
    };
    document.body.appendChild(script);

    return () => {
      stylesheet.remove();
      script.remove();
    };
  }, []);

  return (
    <main className="min-h-screen bg-white">
      <header className="border-b border-slate-200 px-6 py-4">
        <h1 className="text-xl font-semibold text-slate-900">BackTestBench API</h1>
        <p className="mt-1 text-sm text-slate-600">
          Interactive OpenAPI docs for the live Next.js dashboard routes. Planned FastAPI endpoints
          are tagged <strong>Planned</strong>.
        </p>
      </header>
      <div id="swagger-ui" />
    </main>
  );
}
