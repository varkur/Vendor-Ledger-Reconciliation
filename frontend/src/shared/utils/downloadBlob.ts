/**
 * Robustly trigger a browser download for a Blob/response body.
 *
 * Handles quirks that cause "Couldn't download - No permissions" or aborted
 * saves in some browsers:
 *  - Sets an explicit MIME type on the Blob.
 *  - Appends the anchor to the DOM before clicking.
 *  - Delays revoking the object URL so the browser finishes writing the file.
 */
export function downloadBlob(
  data: BlobPart,
  filename: string,
  mimeType = 'application/octet-stream',
): void {
  const blob = data instanceof Blob ? data : new Blob([data], { type: mimeType });
  const url = window.URL.createObjectURL(blob);

  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.rel = 'noopener';
  link.style.display = 'none';
  document.body.appendChild(link);
  link.click();

  // Give the browser time to start the download before cleanup.
  setTimeout(() => {
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
  }, 2000);
}

/** Extract a filename from a Content-Disposition header, with a fallback. */
export function filenameFromDisposition(
  disposition: string | undefined,
  fallback: string,
): string {
  if (!disposition) return fallback;
  // Prefer RFC 5987 (filename*=) then plain filename=
  const star = /filename\*=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  if (star && star[1]) {
    try {
      return decodeURIComponent(star[1]);
    } catch {
      return star[1];
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(disposition);
  return plain && plain[1] ? plain[1] : fallback;
}
