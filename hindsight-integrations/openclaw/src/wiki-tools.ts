/**
 * Wiki tools for OpenClaw agents.
 *
 * Registered as a ToolFactory — called per session with agent context.
 * Resolves bank ID using the same deriveBankId logic as retain/recall,
 * then creates tools scoped to that bank.
 */

import type { PluginConfig, PluginToolContext } from "./types.js";
import { deriveBankId, detectExternalApi } from "./index.js";

// Opinionated defaults for wiki pages
const WIKI_TRIGGER = {
  mode: "delta",
  refresh_after_consolidation: true,
  exclude_mental_models: true,
  fact_types: ["observation"],
};

interface WikiToolDeps {
  pluginConfig: PluginConfig;
  getApiUrl: () => string;
  getApiToken: () => string | undefined;
}

function makeRequest(
  apiUrl: string,
  path: string,
  method: string,
  body?: unknown,
  apiToken?: string,
): Promise<unknown> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (apiToken) headers["Authorization"] = `Bearer ${apiToken}`;

  const opts: RequestInit = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  return fetch(`${apiUrl}${path}`, opts).then(async (resp) => {
    if (!resp.ok) {
      const text = await resp.text().catch(() => "");
      throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json();
  });
}

export function createWikiToolFactory(deps: WikiToolDeps) {
  return (ctx: PluginToolContext) => {
    // Resolve bank from agent context (same logic as retain/recall hooks)
    const bankId = deriveBankId(ctx as any, deps.pluginConfig);
    const apiUrl = deps.getApiUrl();
    const apiToken = deps.getApiToken();

    const bankPath = `/v1/default/banks/${bankId}`;

    const tools: any[] = [
      {
        name: "hindsight_wiki_list",
        label: "List wiki pages",
        description: "List all knowledge pages. Returns page names, IDs, source queries, and content.",
        parameters: { type: "object", properties: {} },
        async execute() {
          const result = await makeRequest(apiUrl, `${bankPath}/mental-models`, "GET", undefined, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_get",
        label: "Get wiki page",
        description: "Get a specific knowledge page by ID.",
        parameters: {
          type: "object",
          properties: {
            page_id: { type: "string", description: "Page identifier" },
          },
          required: ["page_id"],
        },
        async execute(_id: string, params: { page_id: string }) {
          const result = await makeRequest(apiUrl, `${bankPath}/mental-models/${params.page_id}`, "GET", undefined, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_create",
        label: "Create wiki page",
        description:
          "Create a new knowledge page. The source_query is the question the system re-asks after every consolidation to rebuild the page from observations.",
        parameters: {
          type: "object",
          properties: {
            page_id: { type: "string", description: "Page ID (lowercase with hyphens, e.g. 'user-preferences')" },
            name: { type: "string", description: "Human-readable page name" },
            source_query: { type: "string", description: "Synthesis query — the question that rebuilds this page" },
          },
          required: ["page_id", "name", "source_query"],
        },
        async execute(_id: string, params: { page_id: string; name: string; source_query: string }) {
          const result = await makeRequest(apiUrl, `${bankPath}/mental-models`, "POST", {
            id: params.page_id,
            name: params.name,
            source_query: params.source_query,
            max_tokens: 4096,
            trigger: WIKI_TRIGGER,
          }, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_update",
        label: "Update wiki page",
        description: "Update a knowledge page's name or source query.",
        parameters: {
          type: "object",
          properties: {
            page_id: { type: "string", description: "Page identifier" },
            name: { type: "string", description: "New page name" },
            source_query: { type: "string", description: "New synthesis query" },
          },
          required: ["page_id"],
        },
        async execute(_id: string, params: { page_id: string; name?: string; source_query?: string }) {
          const body: Record<string, string> = {};
          if (params.name) body.name = params.name;
          if (params.source_query) body.source_query = params.source_query;
          const result = await makeRequest(apiUrl, `${bankPath}/mental-models/${params.page_id}`, "PATCH", body, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_delete",
        label: "Delete wiki page",
        description: "Delete a knowledge page.",
        parameters: {
          type: "object",
          properties: {
            page_id: { type: "string", description: "Page identifier" },
          },
          required: ["page_id"],
        },
        async execute(_id: string, params: { page_id: string }) {
          await makeRequest(apiUrl, `${bankPath}/mental-models/${params.page_id}`, "DELETE", undefined, apiToken);
          return { content: [{ type: "text", text: JSON.stringify({ success: true }) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_recall",
        label: "Search memories",
        description: "Search agent memories for specific facts, numbers, or details.",
        parameters: {
          type: "object",
          properties: {
            query: { type: "string", description: "Natural language search query" },
            max_results: { type: "number", description: "Maximum results (default: 10)" },
          },
          required: ["query"],
        },
        async execute(_id: string, params: { query: string; max_results?: number }) {
          const result = await makeRequest(apiUrl, `${bankPath}/memories/recall`, "POST", {
            query: params.query,
            max_results: params.max_results ?? 10,
          }, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
      {
        name: "hindsight_wiki_ingest",
        label: "Ingest document",
        description:
          "Upload a document into agent memory. Pass raw content — never summarize before ingesting. The system handles extraction.",
        parameters: {
          type: "object",
          properties: {
            title: { type: "string", description: "Document title (used as document ID for upsert)" },
            content: { type: "string", description: "Raw document content" },
          },
          required: ["title", "content"],
        },
        async execute(_id: string, params: { title: string; content: string }) {
          const docId = params.title.toLowerCase().replace(/ /g, "-");
          const result = await makeRequest(apiUrl, `${bankPath}/memories`, "POST", {
            items: [{ content: params.content, document_id: docId }],
            async: true,
          }, apiToken);
          return { content: [{ type: "text", text: JSON.stringify(result, null, 2) }], details: {} };
        },
      },
    ];

    return tools;
  };
}
