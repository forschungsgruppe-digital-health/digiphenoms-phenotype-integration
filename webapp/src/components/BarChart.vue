<script setup>
/**
 * Horizontal bar list (magnitude, single hue): bars ≤24px thick with a
 * 4px rounded data-end and a square baseline, value at the bar tip,
 * per-mark hover tooltip. Labels/values wear text tokens, never the
 * series color.
 */
import { computed, ref } from "vue";

const props = defineProps({
  // [{ label, value }]
  items: { type: Array, required: true },
  unit: { type: String, default: "" },
  decimals: { type: Number, default: 1 },
});

const maxValue = computed(() =>
  Math.max(...props.items.map((i) => Math.abs(i.value)), 1e-9),
);

const fmt = (v) =>
  v.toLocaleString("de-DE", {
    minimumFractionDigits: 0,
    maximumFractionDigits: props.decimals,
  });

const hover = ref(null); // { label, value, clientX, clientY }

function onMove(item, event) {
  hover.value = {
    label: item.label,
    value: fmt(item.value),
    clientX: event.clientX,
    clientY: event.clientY,
  };
}
</script>

<template>
  <div v-if="items.length === 0" class="empty-note">Keine Messwerte vorhanden.</div>
  <div v-else class="bar-list">
    <div
      v-for="item in items"
      :key="item.label"
      class="bar-row"
      :class="{ lifted: hover && hover.label === item.label }"
      @pointermove="onMove(item, $event)"
      @pointerleave="hover = null"
    >
      <span class="bar-label" :title="item.label">{{ item.label }}</span>
      <span class="bar-track">
        <span
          class="bar-fill"
          :style="{ width: `${(Math.abs(item.value) / maxValue) * 100}%` }"
        ></span>
      </span>
      <span class="bar-value">{{ fmt(item.value) }}{{ unit ? " " + unit : "" }}</span>
    </div>

    <Teleport to="body">
      <div
        v-if="hover"
        class="viz-tooltip"
        :style="{ left: `${hover.clientX + 14}px`, top: `${hover.clientY + 14}px` }"
      >
        <div class="t-row">
          <span class="t-key" style="background: var(--series-1)"></span>
          <span class="t-val">{{ hover.value }}{{ unit ? " " + unit : "" }}</span>
          <span class="t-name">{{ hover.label }}</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.bar-row {
  display: grid;
  grid-template-columns: 170px 1fr 90px;
  align-items: center;
  gap: 10px;
  padding: 4px 0; /* hit target taller than the 18px mark */
}

.bar-label {
  font-size: 12.5px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bar-track {
  display: block;
}

.bar-fill {
  display: block;
  height: 18px;
  background: var(--series-1);
  border-radius: 0 4px 4px 0; /* square baseline, rounded data end */
  min-width: 2px;
}

.bar-row.lifted .bar-fill {
  filter: brightness(1.12);
}

.bar-value {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--text-primary);
}
</style>
