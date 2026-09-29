import { handleAccessStatus } from "../../src/worker.js";

export async function onRequestGet(context) {
  return await handleAccessStatus(context.request);
}
