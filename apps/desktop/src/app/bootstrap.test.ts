import { expect, it } from "vitest";
import { createMockRpcClient } from "../rpc";

it("bootstrap_rejects_protocol_mismatch", async () => {
  const { bootstrapApp } = await import("./bootstrap");
  const client = createMockRpcClient({});
  const call = client.call.bind(client);
  client.call = async (...args) => {
    const value = await call(...args);
    return { ...value, protocolVersion: "2.0" } as typeof value;
  };
  await expect(bootstrapApp(client)).rejects.toMatchObject({
    code: "INTERNAL", data: { reason: "PROTOCOL_MISMATCH", messageKey: "common.protocolMismatch" },
  });
  client.dispose();
});
