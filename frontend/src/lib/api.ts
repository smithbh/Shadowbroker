// All API calls use relative paths (e.g. /api/flights).
// Next.js rewrites them at the server level to BACKEND_URL (set in docker-compose
// or .env.local for dev). This means:
//   - No build-time baking of the backend URL into the client bundle
//   - BACKEND_URL=http://backend:8000 works via Docker internal networking
//   - Only port 3000 needs to be exposed externally
export const API_BASE = "";
