import { handleExecuteDownload } from "../../../src/worker.js";

export async function onRequestGet(context) {
  const token = context.params.token;
  return await handleExecuteDownload(token, context.request);
}
