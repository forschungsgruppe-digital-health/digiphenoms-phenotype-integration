<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, required: true },
});

// status color + icon + text label — state is never color alone
const STATES = {
  completed: { icon: "✓", label: "Abgeschlossen", varName: "--status-good" },
  running: { icon: "▸", label: "Läuft", varName: "--status-warning" },
  queued: { icon: "◌", label: "Wartend", varName: "--text-muted" },
  failed: { icon: "✕", label: "Fehlgeschlagen", varName: "--status-critical" },
};

const state = computed(
  () => STATES[props.status] ?? { icon: "?", label: props.status, varName: "--text-muted" },
);
</script>

<template>
  <span class="status-badge">
    <span class="dot" :style="{ color: `var(${state.varName})` }" aria-hidden="true">
      {{ state.icon }}
    </span>
    <span>{{ state.label }}</span>
  </span>
</template>
