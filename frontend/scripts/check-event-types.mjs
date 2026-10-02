// Fails if the console's event types differ from the CARCUX-BD dataset schema,
// which the backend is already tested against. Run from frontend/.
import { readFileSync } from "node:fs";

const schema = JSON.parse(readFileSync("../data/schema/v1/common.schema.json", "utf8"));
const expected = new Set(schema.$defs.event_type.enum);

const source = readFileSync("src/lib/event-types.ts", "utf8");
const actual = new Set([...source.matchAll(/value: "([a-z_]+)"/g)].map((m) => m[1]));

const missing = [...expected].filter((t) => !actual.has(t));
const extra = [...actual].filter((t) => !expected.has(t));
if (missing.length || extra.length) {
  console.error("Event types out of sync with data/schema/v1/common.schema.json");
  if (missing.length) console.error("  missing in console:", missing.join(", "));
  if (extra.length) console.error("  unknown in console:", extra.join(", "));
  process.exit(1);
}
console.log(`Event types in sync (${expected.size}).`);
