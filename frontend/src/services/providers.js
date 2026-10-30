// Provider / model options shared by the header and the mobile sidebar. The live lists come from
// the backend's /config (edited in the admin panel); the constants here are only fallbacks.

export const HOSTED = 'hosted'

export const PROVIDER_LABELS = {
  openai: 'OpenAI',
  anthropic: 'Claude (Anthropic)',
  ollama_cloud: 'Ollama Cloud',
}

export const API_KEY_PLACEHOLDER = {
  openai: 'sk-... (OpenAI key)',
  anthropic: 'sk-ant-... (Anthropic key)',
  ollama_cloud: 'Ollama Cloud key',
  '': 'Select a provider first',
}

const FALLBACK_MODELS = {
  openai: ['gpt-4.1-mini', 'gpt-4.1', 'gpt-4o-mini', 'o4-mini'],
  anthropic: ['claude-sonnet-4-6', 'claude-haiku-4-5-20251001', 'claude-opus-4-8'],
  ollama_cloud: ['gemma4:31b', 'gpt-oss:120b', 'nemotron-3-super', 'gpt-oss:20b'],
}

export function providerOptions(appConfig) {
  const options = []
  if (appConfig?.hosted) {
    options.push({ value: HOSTED, label: `${appConfig.hosted.label} — no key needed` })
  }
  const byok = appConfig?.byok
  const list = byok ? (byok.enabled ? byok.providers : []) : Object.keys(PROVIDER_LABELS)
  for (const p of list) {
    if (PROVIDER_LABELS[p]) options.push({ value: p, label: PROVIDER_LABELS[p] })
  }
  return options
}

export function modelSuggestions(appConfig, provider) {
  return appConfig?.byok?.suggested_models?.[provider] || FALLBACK_MODELS[provider] || []
}

export function hostedNote(appConfig) {
  const h = appConfig?.hosted
  if (!h) return ''
  const left = h.remaining == null ? '' : `${h.remaining} of ${h.daily_limit} free questions left today. `
  return `${left}Answers use ${h.model} on DocLens's own key, so you don't need one. Add your own key any time for unlimited use.`
}
