<script setup>
defineProps({
  label: { type: String, required: true },
  value: { type: [Number, String], required: true },
  hint: { type: String, default: "" },
});
</script>

<template>
  <div class="stat-tile">
    <div class="label">{{ label }}</div>
    <div class="value">{{ value }}</div>
    <div v-if="hint" class="hint">{{ hint }}</div>
  </div>
</template>
