const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000";

export function getApiBaseUrl(
  env: ImportMetaEnv = import.meta.env,
): string {
  const configured = env.VITE_API_BASE_URL?.trim();

  if (!configured) {
    return DEFAULT_API_BASE_URL;
  }

  return configured.replace(/\/+$/, "");
}
