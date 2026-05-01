function resizeCanvas(canvas) {
  const rect = canvas.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.floor(rect.width * dpr));
  const height = Math.max(1, Math.floor(rect.height * dpr));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  return { width, height, dpr };
}

function drawLine(ctx, points, color, lineWidth) {
  if (points.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i += 1) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.strokeStyle = color;
  ctx.lineWidth = lineWidth;
  ctx.stroke();
}

function drawFill(ctx, points, fillColor, height) {
  if (points.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(points[0].x, height);
  ctx.lineTo(points[0].x, points[0].y);
  for (let i = 1; i < points.length; i += 1) {
    ctx.lineTo(points[i].x, points[i].y);
  }
  ctx.lineTo(points[points.length - 1].x, height);
  ctx.closePath();
  ctx.fillStyle = fillColor;
  ctx.fill();
}

export class LineChart {
  constructor(canvas, { series, minY = 0, maxY = null, padding = 6 } = {}) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.series = series || [];
    this.minY = minY;
    this.maxY = maxY;
    this.padding = padding;
  }

  render() {
    const { width, height } = resizeCanvas(this.canvas);
    const ctx = this.ctx;
    if (!ctx) return;

    ctx.clearRect(0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";

    const maxY = this.maxY ?? this._computeMaxY() ?? 1;
    const minY = this.minY ?? 0;
    const yRange = Math.max(1e-9, maxY - minY);

    const left = this.padding;
    const right = width - this.padding;
    const top = this.padding;
    const bottom = height - this.padding;

    const xRange = Math.max(1, right - left);
    const yRangePx = Math.max(1, bottom - top);

    for (const s of this.series) {
      const data = Array.isArray(s.data) ? s.data : [];
      if (data.length < 2) continue;

      const points = data.map((v, i) => {
        const x = left + (i / (data.length - 1)) * xRange;
        const y = bottom - ((Number(v) - minY) / yRange) * yRangePx;
        return { x, y };
      });

      if (s.fill) drawFill(ctx, points, s.fill, bottom);
      drawLine(ctx, points, s.stroke || "#58a6ff", s.width || 2);
    }
  }

  _computeMaxY() {
    let max = null;
    for (const s of this.series) {
      const data = Array.isArray(s.data) ? s.data : [];
      for (const v of data) {
        const n = Number(v);
        if (!Number.isFinite(n)) continue;
        if (max === null || n > max) max = n;
      }
    }
    return max;
  }
}

