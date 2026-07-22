const test = require("node:test");
const assert = require("node:assert/strict");

const { selectMessageCursorFunction } = require("../src/wcdb-sidecar.cjs");

test("WCDB sidecar falls back from the lite cursor to the regular cursor", () => {
  const regular = () => 0;
  const selected = selectMessageCursorFunction("open_message_cursor_lite", {
    wcdb_open_message_cursor: regular,
  });

  assert.equal(selected.fnName, "wcdb_open_message_cursor");
  assert.equal(selected.fn, regular);
});

test("WCDB sidecar prefers the lite cursor when the native library exports it", () => {
  const regular = () => 0;
  const lite = () => 0;
  const selected = selectMessageCursorFunction("open_message_cursor_lite", {
    wcdb_open_message_cursor: regular,
    wcdb_open_message_cursor_lite: lite,
  });

  assert.equal(selected.fnName, "wcdb_open_message_cursor_lite");
  assert.equal(selected.fn, lite);
});
