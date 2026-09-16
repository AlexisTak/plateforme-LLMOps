/**
 * Minimal example client for Biscuits Focus's HTTP API.
 *
 * No separate hand-maintained package here: generate a typed client from the
 * OpenAPI schema with any standard tool instead of hand-maintaining (and
 * inevitably drifting from) a second implementation, e.g.:
 *
 *   npx openapi-typescript http://localhost:8000/openapi.json -o schema.d.ts
 *
 * /api/v1/* mirrors every endpoint under a stable, versioned prefix
 * (api/main.py's ApiV1AliasMiddleware) — point codegen at either prefix.
 * The one thing codegen can't infer is the auth header contract, demonstrated
 * below (see api/enterprise.py:actor_from_request for the authoritative version).
 *
 * Run: npx tsx sdk/typescript/quickstart.ts
 */

const BASE_URL = process.env.BISCUITS_FOCUS_URL ?? "http://localhost:8000";

function headers(): Record<string, string> {
  // local mode (the default) needs no headers at all. proxy mode needs the
  // identity headers your reverse proxy / SSO gateway is expected to set.
  const proxySecret = process.env.BISCUITS_PROXY_SECRET;
  if (!proxySecret) return {};
  return {
    "x-biscuits-proxy-secret": proxySecret,
    "x-biscuits-user-id": process.env.BISCUITS_USER_ID ?? "",
    "x-biscuits-user-email": process.env.BISCUITS_USER_EMAIL ?? "",
    "x-biscuits-role": process.env.BISCUITS_USER_ROLE ?? "viewer",
  };
}

async function listProjects(): Promise<{ id: string }[]> {
  const response = await fetch(`${BASE_URL}/api/v1/projects`, { headers: headers() });
  if (!response.ok) throw new Error(`GET /api/v1/projects failed: ${response.status}`);
  return response.json();
}

async function demo() {
  const projects = await listProjects();
  console.log(`${projects.length} project(s): ${projects.map((p) => p.id).join(", ")}`);
}

demo();
