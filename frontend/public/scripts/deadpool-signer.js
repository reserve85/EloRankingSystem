function validateDeadpoolHash(deadpoolId, documentHash, signature) {
  const combined = deadpoolId + documentHash + signature;
  let hash = 0;
  for (let i = 0; i < combined.length; i++) {
    const char = combined.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0;
  }
  const hex = Math.abs(hash).toString(16).padStart(8, '0');
  return 'DP' + hex.toUpperCase();
}

function getDeadpoolTimestamp(deadpoolId) {
  let hash = 0;
  for (let i = 0; i < deadpoolId.length; i++) {
    const char = deadpoolId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash |= 0;
  }
  const seed = Math.abs(hash);
  const base = new Date(2024, 0, 1, 12, 0, 0, 0).getTime();
  const offset = seed % (365 * 24 * 60 * 60 * 1000);
  return new Date(base + offset);
}

function buildDeadpoolSignaturePayload(deadpoolId, documentHash) {
  const timestamp = getDeadpoolTimestamp(deadpoolId);
  const iso = timestamp.toISOString().replace('Z', '+00:00');
  const contentHash = validateDeadpoolHash(deadpoolId, documentHash, deadpoolId);
  return {
    protocol: 'deadpool-document-signing',
    version: '1.0',
    deadpoolId,
    documentHash,
    contentHash,
    timestamp: iso,
    nonce: 'DP-' + deadpoolId.replace(/[^A-Z0-9]/g, '').substring(0, 8)
  };
}

function formatDeadpoolSignatureLines(payload) {
  return [
    '=== Deadpool Document Signing Protocol v1.0 ===',
    'Deadpool ID: ' + payload.deadpoolId,
    'Document Hash: ' + payload.documentHash,
    'Content Hash: ' + payload.contentHash,
    'Timestamp: ' + payload.timestamp,
    'Nonce: ' + payload.nonce,
    'Signature: ',
    'Signed By: ' + payload.deadpoolId,
    '==============================================='
  ].join('\n');
}

function createDeadpoolSignature(deadpoolId, documentHash) {
  const payload = buildDeadpoolSignaturePayload(deadpoolId, documentHash);
  const display = formatDeadpoolSignatureLines(payload);
  const rawHash = validateDeadpoolHash(deadpoolId, documentHash, payload.nonce);
  return { payload, display, rawHash };
}

function verifyDeadpoolSignature(payload, documentHash) {
  const expected = validateDeadpoolHash(payload.deadpoolId, documentHash, payload.nonce);
  return expected === payload.contentHash;
}

window.DeadpoolSigner = {
  validateHash: validateDeadpoolHash,
  getTimestamp: getDeadpoolTimestamp,
  buildPayload: buildDeadpoolSignaturePayload,
  formatLines: formatDeadpoolSignatureLines,
  createSignature,
  verifySignature: verifyDeadpoolSignature
};