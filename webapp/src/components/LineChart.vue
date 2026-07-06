<script setup>
/**
 * Single-axis SVG line chart per the dataviz specs:
 * 2px round-cap lines, ≥8px markers with a 2px surface ring, hairline
 * solid gridlines, muted tabular ticks, a direct value label at each
 * series end, a legend for ≥2 series, and a crosshair tooltip that
 * snaps to the nearest x and lists every series.
 */
import { computed, ref } from "vue";

const props = defineProps({
  // [{ name, color, points: [{ x: Date, y: Number }] }]
  series: { type: Array, required: true },
  unit: { type: String, default: "" },
  height: { type: Number, default: 190 },
  yDecimals: { type: Number, default: 1 },
});

const W = 640;
const PAD = { top: 12, right: 74, bottom: 24, left: 46 };

const drawable = computed(() =>
  props.series
    .map((s) => ({
      ...s,
      points: [...s.points]
        .filter((p) => p.x instanceof Date && !Number.isNaN(p.x.getTime()) && p.y != null)
        .sort((a, b) => a.x - b.x),
    }))
    .filter((s) => s.points.length > 0),
);

const xDomain = computed(() => {
  const xs = drawable.value.flatMap((s) => s.points.map((p) => p.x.getTime()));
  let lo = Math.min(...xs);
  let hi = Math.max(...xs);
  if (lo === hi) {
    lo -= 43200000; // ±12h around a single timestamp
    hi += 43200000;
  }
  return [lo, hi];
});

function niceTicks(min, max, count = 4) {
  if (min === max) {
    min -= 1;
    max += 1;
  }
  // smallest step from {1,2,5,10}·10^k that yields ≤ count+1 intervals
  const step0 = (max - min) / count;
  const mag = 10 ** Math.floor(Math.log10(step0));
  let step = 10 * mag;
  for (const m of [1, 2, 5, 10]) {
    if (step0 <= m * mag) {
      step = m * mag;
      break;
    }
  }
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(6));
  return { lo, hi, ticks };
}

const yScale = computed(() => {
  const ys = drawable.value.flatMap((s) => s.points.map((p) => p.y));
  const pad = (Math.max(...ys) - Math.min(...ys)) * 0.15 || Math.abs(ys[0]) * 0.1 || 1;
  return niceTicks(Math.min(...ys) - pad, Math.max(...ys) + pad, 4);
});

function sx(t) {
  const [lo, hi] = xDomain.value;
  return PAD.left + ((t - lo) / (hi - lo)) * (W - PAD.left - PAD.right);
}

function sy(v) {
  const { lo, hi } = yScale.value;
  return (
    props.height - PAD.bottom -
    ((v - lo) / (hi - lo)) * (props.height - PAD.top - PAD.bottom)
  );
}

function linePath(points) {
  return points
    .map((p, i) => `${i === 0 ? "M" : "L"} ${sx(p.x.getTime()).toFixed(1)} ${sy(p.y).toFixed(1)}`)
    .join(" ");
}

const fmtValue = (v) =>
  v.toLocaleString("de-DE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: props.yDecimals,
  });

const fmtDate = (t) =>
  new Date(t).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "2-digit" });

const xTicks = computed(() => {
  const [lo, hi] = xDomain.value;
  return lo === hi ? [lo] : [lo, (lo + hi) / 2, hi];
});

/* ---- crosshair + tooltip ---- */
const svgEl = ref(null);
const hover = ref(null); // { t, x, rows: [{name,color,value}], clientX, clientY }

function onMove(event) {
  if (!svgEl.value || drawable.value.length === 0) return;
  const rect = svgEl.value.getBoundingClientRect();
  const px = ((event.clientX - rect.left) / rect.width) * W;
  const candidates = [
    ...new Set(drawable.value.flatMap((s) => s.points.map((p) => p.x.getTime()))),
  ];
  let best = candidates[0];
  for (const t of candidates) {
    if (Math.abs(sx(t) - px) < Math.abs(sx(best) - px)) best = t;
  }
  const rows = drawable.value
    .map((s) => {
      const point = s.points.find((p) => p.x.getTime() === best);
      return point ? { name: s.name, color: s.color, value: fmtValue(point.y) } : null;
    })
    .filter(Boolean);
  hover.value = { t: best, x: sx(best), rows, clientX: event.clientX, clientY: event.clientY };
}

function onLeave() {
  hover.value = null;
}
</script>

<template>
  <div v-if="drawable.length === 0" class="empty-note">Keine Messwerte vorhanden.</div>
  <div v-else>
    <div v-if="drawable.length >= 2" class="legend">
      <span v-for="s in drawable" :key="s.name">
        <span class="key" :style="{ background: s.color }"></span>{{ s.name }}
      </span>
    </div>
    <svg
      ref="svgEl"
      :viewBox="`0 0 ${W} ${height}`"
      style="width: 100%; display: block"
      role="img"
      @pointermove="onMove"
      @pointerleave="onLeave"
    >
      <!-- hairline grid + y ticks -->
      <g v-for="tick in yScale.ticks" :key="tick">
        <line
          :x1="PAD.left"
          :x2="W - PAD.right"
          :y1="sy(tick)"
          :y2="sy(tick)"
          stroke="var(--grid)"
          stroke-width="1"
        />
        <text
          :x="PAD.left - 8"
          :y="sy(tick) + 3.5"
          text-anchor="end"
          font-size="11"
          fill="var(--text-muted)"
          style="font-variant-numeric: tabular-nums"
        >
          {{ fmtValue(tick) }}
        </text>
      </g>

      <!-- x ticks -->
      <text
        v-for="t in xTicks"
        :key="t"
        :x="sx(t)"
        :y="height - 6"
        text-anchor="middle"
        font-size="11"
        fill="var(--text-muted)"
        style="font-variant-numeric: tabular-nums"
      >
        {{ fmtDate(t) }}
      </text>

      <!-- crosshair -->
      <line
        v-if="hover"
        :x1="hover.x"
        :x2="hover.x"
        :y1="PAD.top"
        :y2="height - PAD.bottom"
        stroke="var(--baseline)"
        stroke-width="1"
      />

      <!-- series -->
      <g v-for="s in drawable" :key="s.name">
        <path
          v-if="s.points.length > 1"
          :d="linePath(s.points)"
          fill="none"
          :stroke="s.color"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
        <circle
          v-for="p in s.points"
          :key="p.x.getTime()"
          :cx="sx(p.x.getTime())"
          :cy="sy(p.y)"
          r="4.5"
          :fill="s.color"
          stroke="var(--surface-1)"
          stroke-width="2"
        />
        <!-- direct label at the series end -->
        <text
          :x="sx(s.points[s.points.length - 1].x.getTime()) + 10"
          :y="sy(s.points[s.points.length - 1].y) + 4"
          font-size="12"
          fill="var(--text-secondary)"
          style="font-variant-numeric: tabular-nums"
        >
          {{ fmtValue(s.points[s.points.length - 1].y) }}{{ unit ? " " + unit : "" }}
        </text>
      </g>
    </svg>

    <Teleport to="body">
      <div
        v-if="hover"
        class="viz-tooltip"
        :style="{ left: `${hover.clientX + 14}px`, top: `${hover.clientY + 14}px` }"
      >
        <div class="t-head">{{ fmtDate(hover.t) }}</div>
        <div v-for="row in hover.rows" :key="row.name" class="t-row">
          <span class="t-key" :style="{ background: row.color }"></span>
          <span class="t-val">{{ row.value }}{{ unit ? " " + unit : "" }}</span>
          <span class="t-name">{{ row.name }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>
