/** The full configuration (machine plus evolution parameters) encodes into
 * the URL hash, deflate-compressed and base64url-encoded, so every figure has
 * a link that reproduces it exactly. */

import type { AppState } from "./types.js";

async function pipe(bytes: Uint8Array, stream: ReadableWritablePair<Uint8Array, Uint8Array>) {
  const blob = new Blob([bytes as BlobPart]);
  const compressed = blob.stream().pipeThrough(stream);
  return new Uint8Array(await new Response(compressed).arrayBuffer());
}

function toBase64Url(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replaceAll("+", "-").replaceAll("/", "_").replace(/=+$/, "");
}

function fromBase64Url(text: string): Uint8Array {
  const padded = text.replaceAll("-", "+").replaceAll("_", "/");
  const binary = atob(padded + "=".repeat((4 - (padded.length % 4)) % 4));
  return Uint8Array.from(binary, (c) => c.charCodeAt(0));
}

export async function encodeState(state: AppState): Promise<string> {
  const raw = new TextEncoder().encode(JSON.stringify(state));
  const packed = await pipe(raw, new CompressionStream("deflate-raw"));
  return toBase64Url(packed);
}

export async function decodeState(hash: string): Promise<AppState | null> {
  const text = hash.replace(/^#/, "");
  if (!text) return null;
  try {
    const packed = fromBase64Url(text);
    const raw = await pipe(packed, new DecompressionStream("deflate-raw"));
    return JSON.parse(new TextDecoder().decode(raw)) as AppState;
  } catch {
    return null;
  }
}

export async function writeStateToUrl(state: AppState): Promise<void> {
  const encoded = await encodeState(state);
  history.replaceState(null, "", "#" + encoded);
}
