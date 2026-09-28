import { handleAnalyzeRequest } from "../../../src/worker.js";

export async function onRequestPost(context) {
  return await handleAnalyzeRequest(context.request);
}
