/**
 * Open a dedicated print document for the story manuscript and trigger the browser print dialog.
 */

function escapeHtml(s: string): string {
  return s
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export function printStoryManuscript(opts: { title?: string; manuscript: string }): boolean {
  const title = (opts.title || 'Story manuscript').trim();
  const manuscript = escapeHtml(opts.manuscript);
  const page = `<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>${escapeHtml(title)} - Print</title>
    <style>
      @page { margin: 16mm; }
      html, body { margin: 0; padding: 0; background: #fff; color: #111; }
      body { font-family: Georgia, "Times New Roman", serif; line-height: 1.5; font-size: 12pt; }
      main { max-width: 7in; margin: 0 auto; }
      h1 { font-size: 20pt; margin: 0 0 0.5rem; font-weight: 600; }
      p.meta { margin: 0 0 1rem; color: #444; font-size: 10pt; }
      pre {
        margin: 0;
        white-space: pre-wrap;
        word-wrap: break-word;
        overflow-wrap: anywhere;
        font-family: inherit;
        font-size: 12pt;
      }
      @media print {
        body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      }
    </style>
  </head>
  <body>
    <main>
      <h1>${escapeHtml(title)}</h1>
      <p class="meta">Story manuscript</p>
      <pre>${manuscript}</pre>
    </main>
  </body>
</html>`;

  const frame = document.createElement('iframe');
  frame.setAttribute('aria-hidden', 'true');
  frame.style.position = 'fixed';
  frame.style.right = '0';
  frame.style.bottom = '0';
  frame.style.width = '0';
  frame.style.height = '0';
  frame.style.border = '0';
  frame.style.visibility = 'hidden';
  document.body.appendChild(frame);

  const cleanup = () => {
    try {
      frame.remove();
    } catch {
      /* ignore */
    }
  };

  const doc = frame.contentDocument;
  const win = frame.contentWindow;
  if (!doc || !win) {
    cleanup();
    return false;
  }
  doc.open();
  doc.write(page);
  doc.close();

  const trigger = () => {
    try {
      win.focus();
      win.print();
    } finally {
      setTimeout(cleanup, 1000);
    }
  };
  if (doc.readyState === 'complete') {
    setTimeout(trigger, 60);
  } else {
    frame.addEventListener('load', () => setTimeout(trigger, 60), { once: true });
  }
  return true;
}

