// Demo access: one shared passphrase, no user accounts (out of scope). The cookie holds a
// hash of the passphrase, never the passphrase itself. Fails closed: without
// DEMO_PASSPHRASE configured, nobody gets in.

export const GATE_COOKIE = "demo_gate";

export async function gateToken(passphrase: string): Promise<string> {
  const data = new TextEncoder().encode(`invoice-demo:${passphrase}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
}

export async function expectedToken(): Promise<string | null> {
  const passphrase = process.env.DEMO_PASSPHRASE;
  return passphrase ? gateToken(passphrase) : null;
}
