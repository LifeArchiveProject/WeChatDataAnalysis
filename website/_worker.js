export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    const stream = path === "/api/release-notes/events";
    if (path !== "/api/release-notes" && !stream) return env.ASSETS.fetch(request);

    const headers = { "Cache-Control": "no-store, no-transform", "X-Content-Type-Options": "nosniff" };
    if (request.method !== "GET") {
      return new Response(null, { status: 405, headers: { ...headers, Allow: "GET" } });
    }

    const accept = stream ? "text/event-stream" : "application/json";
    try {
      const url = new URL(env.CHANGELOG_URL);
      if (stream) {
        url.pathname += "/events";
        url.search = "";
      }
      const upstream = await fetch(url, {
        headers: { Accept: accept },
        cache: "no-store",
        redirect: "manual",
        signal: request.signal,
      });
      const contentType = upstream.headers.get("Content-Type");
      if (upstream.status !== 200 || contentType?.split(";")[0] !== accept) {
        throw new Error("Invalid release notes response");
      }
      return new Response(upstream.body, { headers: { ...headers, "Content-Type": contentType } });
    } catch {
      // 流暂不可用时关闭连接，由浏览器重连。
      if (stream) return new Response(null, { headers: { ...headers, "Content-Type": accept } });
      return Response.json({ error: "更新日志暂时无法获取" }, { status: 502, headers });
    }
  },
};
