// vitarehab.org serves static files. Safari only plays <video> when the server answers byte-range requests with 206,
// which static assets alone do not do, so requests under /pitch/assets/ come here and get sliced.
export default {
  async fetch(req, env) {
    const res = await env.ASSETS.fetch(req);
    const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.get('Range') || '');
    if (res.status !== 200) return res;
    if (!m) { const out = new Response(res.body, res); out.headers.set('Accept-Ranges', 'bytes'); return out; }
    const buf = await res.arrayBuffer(), size = buf.byteLength;
    const start = m[1] === '' ? Math.max(0, size - Number(m[2])) : Number(m[1]);
    const end = m[1] === '' || m[2] === '' ? size - 1 : Math.min(Number(m[2]), size - 1);
    if (m[1] === '' && m[2] === '' || start > end) return new Response(null, { status: 416, headers: { 'Content-Range': `bytes */${size}` } });
    const h = new Headers(res.headers);
    h.set('Accept-Ranges', 'bytes'); h.set('Content-Range', `bytes ${start}-${end}/${size}`); h.set('Content-Length', String(end - start + 1));
    return new Response(buf.slice(start, end + 1), { status: 206, headers: h });
  },
};
