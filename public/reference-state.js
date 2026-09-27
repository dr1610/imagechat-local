// Advance the editable image while retaining the numbered auxiliary references.
export function nextEditReferences(assetId, previous = []) {
  return [assetId, ...previous.slice(1).filter(id => id !== assetId)];
}
