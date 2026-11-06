const url = "/api/release-notes";

export function watchReleaseNotes(render, unavailable) {
  let renderedRevision;
  let announcedRevision;
  let loading = false;

  async function refresh() {
    if (loading) return;
    loading = true;
    const requestedRevision = announcedRevision;
    try {
      const response = await fetch(url, { cache: "no-store" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      const { items, revision } = await response.json();
      if (typeof revision !== "string" || !Array.isArray(items)) throw new Error("更新日志数据不完整");
      // 读取期间收到通知时，只采用已包含该版本的响应。
      if (announcedRevision !== requestedRevision && revision !== announcedRevision) return;
      if (revision !== renderedRevision) {
        render(items.filter((item) => item.changes.length));
        renderedRevision = revision;
      }
    } catch {
      if (renderedRevision === undefined) unavailable?.();
    } finally {
      loading = false;
      if (announcedRevision !== requestedRevision && announcedRevision !== renderedRevision) void refresh();
    }
  }

  const events = new EventSource(url + "/events");
  events.addEventListener("changed", ({ data }) => {
    announcedRevision = JSON.parse(data).revision;
    if (announcedRevision !== renderedRevision) void refresh();
  });
  void refresh();
}
