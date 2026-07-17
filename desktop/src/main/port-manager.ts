import net from "node:net";
import { DesktopError } from "./errors.js";

export async function allocateLoopbackPort(): Promise<number> {
  return await new Promise<number>((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", (error) => {
      reject(
        new DesktopError(
          "PORT_ALLOCATION_FAILED",
          "Unable to allocate a local port for OpenXFlow.",
          error,
        ),
      );
    });
    server.listen({ host: "127.0.0.1", port: 0, exclusive: true }, () => {
      const address = server.address();
      if (!address || typeof address === "string") {
        server.close();
        reject(new DesktopError("PORT_ALLOCATION_FAILED", "Invalid local port response."));
        return;
      }
      const { port } = address;
      server.close((error) => {
        if (error) {
          reject(
            new DesktopError(
              "PORT_ALLOCATION_FAILED",
              "Unable to release the allocated local port.",
              error,
            ),
          );
          return;
        }
        resolve(port);
      });
    });
  });
}
