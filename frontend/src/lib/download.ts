/** Browser-side download helpers for exporting logs, tables and charts. */

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadText(text: string, filename: string, mime = 'text/plain'): void {
  downloadBlob(new Blob([text], { type: `${mime};charset=utf-8` }), filename);
}

function csvCell(value: unknown): string {
  if (value === null || value === undefined) return '';
  const s = String(value);
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(headers: string[], rows: unknown[][]): string {
  return [headers, ...rows].map((r) => r.map(csvCell).join(',')).join('\n') + '\n';
}

export function downloadCsv(headers: string[], rows: unknown[][], filename: string): void {
  downloadText(toCsv(headers, rows), filename, 'text/csv');
}

/**
 * Serialize an on-screen SVG into a standalone file. CSS variables and Tailwind
 * classes don't survive outside the page, so computed colors are inlined and a
 * solid background is added.
 */
function serializeSvg(svg: SVGSVGElement, background: string): { markup: string; width: number; height: number } {
  const clone = svg.cloneNode(true) as SVGSVGElement;
  const srcNodes = svg.querySelectorAll('*');
  const dstNodes = clone.querySelectorAll('*');
  srcNodes.forEach((node, i) => {
    const cs = window.getComputedStyle(node as Element);
    const dst = dstNodes[i] as SVGElement;
    for (const prop of ['stroke', 'fill', 'stroke-width', 'stroke-dasharray', 'font-size', 'font-family']) {
      const v = cs.getPropertyValue(prop);
      if (v) dst.style.setProperty(prop, v);
    }
  });

  const vb = svg.viewBox.baseVal;
  const width = vb && vb.width ? vb.width : svg.clientWidth;
  const height = vb && vb.height ? vb.height : svg.clientHeight;
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  clone.setAttribute('width', String(width));
  clone.setAttribute('height', String(height));
  clone.removeAttribute('class');

  const bg = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  bg.setAttribute('x', vb && vb.width ? String(vb.x) : '0');
  bg.setAttribute('y', vb && vb.height ? String(vb.y) : '0');
  bg.setAttribute('width', String(width));
  bg.setAttribute('height', String(height));
  bg.setAttribute('fill', background);
  clone.insertBefore(bg, clone.firstChild);

  return { markup: new XMLSerializer().serializeToString(clone), width, height };
}

function pageBackground(): string {
  return window.getComputedStyle(document.body).backgroundColor || '#ffffff';
}

export function downloadSvg(svg: SVGSVGElement, filename: string): void {
  const { markup } = serializeSvg(svg, pageBackground());
  downloadText(markup, filename, 'image/svg+xml');
}

export async function downloadSvgAsPng(svg: SVGSVGElement, filename: string, scale = 3): Promise<void> {
  const { markup, width, height } = serializeSvg(svg, pageBackground());
  const img = new Image();
  const url = URL.createObjectURL(new Blob([markup], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    await new Promise<void>((resolve, reject) => {
      img.onload = () => resolve();
      img.onerror = () => reject(new Error('Could not render chart image'));
      img.src = url;
    });
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('Canvas is not available');
    ctx.scale(scale, scale);
    ctx.drawImage(img, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/png'));
    if (!blob) throw new Error('PNG encoding failed');
    downloadBlob(blob, filename);
  } finally {
    URL.revokeObjectURL(url);
  }
}

/** Make a string safe to use as a file name. */
export function safeFilename(name: string): string {
  return name.replace(/[^a-zA-Z0-9_.-]+/g, '_').replace(/_+/g, '_');
}
