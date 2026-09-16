/* Shared session storage and JSON request helpers for all frontend pages. */
(function () {
  const TOKEN_KEY = "cinema_club_token";

  function getToken() {
    return localStorage.getItem(TOKEN_KEY);
  }

  function setToken(token) {
    localStorage.setItem(TOKEN_KEY, token);
  }

  function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
  }

  function authHeaders() {
    const token = getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }

  async function errorFor(response) {
    let detail = `HTTP ${response.status}`;
    try {
      const payload = response.headers.get("content-type")?.includes("application/json")
        ? await response.json()
        : await response.text();
      detail = typeof payload === "string"
        ? (payload || detail)
        : String(payload?.detail ?? payload?.message ?? detail);
    } catch {}
    return Object.assign(new Error(detail), { status: response.status });
  }

  async function request(path, { method = "GET", body, auth = false, headers = {} } = {}) {
    const requestHeaders = { ...headers };
    if (auth) Object.assign(requestHeaders, authHeaders());
    if (body !== undefined) requestHeaders["Content-Type"] = "application/json";

    const response = await fetch(path, {
      method,
      headers: requestHeaders,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!response.ok) throw await errorFor(response);
    return response.status === 204 ? null : response.json();
  }

  window.CinemaApi = Object.freeze({
    getToken,
    setToken,
    clearToken,
    authHeaders,
    request,
  });
})();
