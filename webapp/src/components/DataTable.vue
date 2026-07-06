<script setup>
defineProps({
  // [{ key, label }]
  columns: { type: Array, required: true },
  // [{ [key]: value }]
  rows: { type: Array, required: true },
});
</script>

<template>
  <div style="overflow-x: auto">
    <table>
      <thead>
        <tr>
          <th v-for="col in columns" :key="col.key">{{ col.label }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(row, i) in rows" :key="i">
          <td v-for="col in columns" :key="col.key">{{ row[col.key] ?? "—" }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
