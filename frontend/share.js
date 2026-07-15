// Shared spreadsheet-export helpers (D.3). Fetch a backend-built .xlsx as a blob
// and hand it to the OS share sheet (Sheets / Numbers / Files) on mobile, or
// download it on desktop. Kept out of api.js because api.js's request() forces
// a JSON response, which is unusable for a binary download.
import { showToast } from "./toast.js";

const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

// Prefer the server-provided filename (Content-Disposition), else a fallback.
function filenameFrom(res, fallback) {
  const cd = res.headers.get("Content-Disposition") || "";
  const m = /filename="?([^"]+?)"?$/.exec(cd.split(";").pop()?.trim() || "");
  return (m && m[1]) || fallback;
}

function downloadBlob(blob, filename) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// Fetch `path` (relative to /api) as an .xlsx, then share (mobile) or download.
export async function exportSpreadsheet(path, { fallbackName = "stats.xlsx", title = "Stats" } = {}) {
  let res;
  try {
    res = await fetch("/api" + path);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
  } catch {
    showToast("Couldn't build the export — check your connection.");
    return;
  }
  const blob = await res.blob();
  const filename = filenameFrom(res, fallbackName);
  const file = new File([blob], filename, { type: XLSX_MIME });

  // Native share sheet → Open in Sheets / Numbers / Files, where supported.
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title });
      return;
    } catch (err) {
      // The user dismissed the share sheet — done; don't also download.
      if (err && err.name === "AbortError") return;
      // Any other failure (commonly the user-activation being consumed by the
      // await above → NotAllowedError) falls through to a plain download so the
      // coach always gets the file instead of the button seeming to do nothing.
    }
  }
  downloadBlob(blob, filename);
}
