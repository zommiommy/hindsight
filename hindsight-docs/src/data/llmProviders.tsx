import type {IconType} from 'react-icons';
import React from 'react';
import {SiOpenai, SiAnthropic, SiGooglegemini, SiOllama} from 'react-icons/si';
import {LuTerminal, LuZap, LuBrainCog, LuSparkles, LuGlobe, LuLayers, LuCloud} from 'react-icons/lu';

const OpenAICompatibleIcon: IconType = ({size = 28, ...props}) => (
  <span style={{position: 'relative', display: 'inline-flex'}}>
    <SiOpenai size={size} {...props} />
    <span style={{
      position: 'absolute', bottom: -3, right: -6,
      fontSize: Math.round((size as number) * 0.5), fontWeight: 900, lineHeight: 1,
      color: 'currentColor',
    }}>+</span>
  </span>
);

export interface LLMProvider {
  /** HINDSIGHT_API_LLM_PROVIDER value, e.g. "deepseek". Empty string for the
   *  "OpenAI Compatible" pseudo-entry which is not a real provider id. */
  id: string;
  /** Display name shown in the grid tile and table. */
  label: string;
  /** Icon component rendered in the grid tile. */
  icon: IconType;
  /** Provider default model. Undefined = no entry in the default-models table
   *  (e.g. OpenAI Compatible has no default; LiteLLM is conceptual). */
  defaultModel?: string;
  /** Optional note rendered in the default-models table. */
  defaultModelNote?: string;
}

/**
 * Single source of truth for the supported LLM providers shown in the docs.
 *
 * Adding a provider here updates both the LLMProvidersGrid icon grid (on the
 * Models page) and the "Provider Default Models" table — no other doc file
 * needs to be touched. Keep aligned with PROVIDER_DEFAULT_MODELS in
 * hindsight-api-slim/hindsight_api/config.py.
 */
export const LLM_PROVIDERS: LLMProvider[] = [
  {id: 'openai',         label: 'OpenAI',          icon: SiOpenai,          defaultModel: 'gpt-4o-mini'},
  {id: 'anthropic',      label: 'Anthropic',       icon: SiAnthropic,       defaultModel: 'claude-haiku-4-5-20251001'},
  {id: 'gemini',         label: 'Google Gemini',   icon: SiGooglegemini,    defaultModel: 'gemini-2.5-flash'},
  {id: 'vertexai',       label: 'Vertex AI',       icon: SiGooglegemini,    defaultModel: 'gemini-2.0-flash-001'},
  {id: 'groq',           label: 'Groq',            icon: LuZap,             defaultModel: 'openai/gpt-oss-120b'},
  {id: 'ollama',         label: 'Ollama',          icon: SiOllama,          defaultModel: 'gemma3:12b'},
  {id: 'lmstudio',       label: 'LM Studio',       icon: LuBrainCog,        defaultModel: 'local-model'},
  {id: 'llamacpp',       label: 'llama.cpp',       icon: LuTerminal,        defaultModel: 'gemma-4-e2b-it', defaultModelNote: 'auto-downloaded GGUF'},
  {id: 'minimax',        label: 'MiniMax',         icon: LuSparkles,        defaultModel: 'MiniMax-M2.7'},
  {id: 'deepseek',       label: 'DeepSeek',        icon: LuBrainCog,        defaultModel: 'deepseek-v4-flash'},
  {id: 'volcano',        label: 'Volcano Engine',  icon: LuZap,             defaultModel: 'doubao-pro-32k'},
  {id: 'openrouter',     label: 'OpenRouter',      icon: LuGlobe,           defaultModel: 'qwen/qwen3.5-9b'},
  {id: 'openai-codex',   label: 'OpenAI Codex',    icon: SiOpenai,          defaultModel: 'gpt-5.2-codex'},
  {id: 'claude-code',    label: 'Claude Code',     icon: SiAnthropic,       defaultModel: 'claude-sonnet-4-5-20250929'},
  {id: 'bedrock',        label: 'AWS Bedrock',     icon: LuCloud,           defaultModel: 'us.amazon.nova-2-lite-v1:0'},
  {id: '',               label: 'OpenAI Compatible', icon: OpenAICompatibleIcon},
  {id: 'litellm',        label: 'LiteLLM (100+)',  icon: LuLayers,          defaultModel: 'gpt-4o-mini'},
];
