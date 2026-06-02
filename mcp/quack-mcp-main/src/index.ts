import { QuackMCPServer } from "./mcp.ts";

export { QuackMCPServer };

import { fileURLToPath } from "url";
import path from "path";

if (path.resolve(process.argv[1] || "") === fileURLToPath(import.meta.url)) {
  const server = new QuackMCPServer();
  server.run().catch(console.error);
}
