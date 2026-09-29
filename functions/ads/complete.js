import { handleAdComplete } from "../../src/worker.js";

export async function onRequestPost(context) {
  return await handleAdComplete(context.request);
}
