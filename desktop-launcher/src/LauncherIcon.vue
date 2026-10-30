<script setup lang="ts">
defineProps<{ name: string }>()
const shapes: Record<string, string> = {
  home: 'm8 5 11 7-11 7Z', versions: 'M4 5h16v14H4zM4 9h16M9 9v10',
  environment: 'M4 6h16M4 12h16M4 18h16M9 3v6M16 9v6M10 15v6',
  logs: 'M6 3h9l4 4v14H6zM14 3v5h5M9 12h7M9 16h7',
  settings: 'M9.73 5.01 10.47 2.32 13.53 2.32 14.27 5.01 15.34 5.45 17.76 4.07 19.93 6.24 18.55 8.66 18.99 9.73 21.68 10.47 21.68 13.53 18.99 14.27 18.55 15.34 19.93 17.76 17.76 19.93 15.34 18.55 14.27 18.99 13.53 21.68 10.47 21.68 9.73 18.99 8.66 18.55 6.24 19.93 4.07 17.76 5.45 15.34 5.01 14.27 2.32 13.53 2.32 10.47 5.01 9.73 5.45 8.66 4.07 6.24 6.24 4.07 8.66 5.45ZM15 12a3 3 0 1 1-6 0a3 3 0 0 1 6 0Z',
  folder: 'M3 6h7l2 2h9v12H3zM3 6V4h7l2 2', refresh: 'M20 10a8 8 0 1 0-2 8M20 4v6h-6',
  copy: 'M9 9h11v12H9zM15 9V3H3v12h6', down: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
  search: 'M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14Zm5-2 6 6',
  arrow: 'm9 5 7 7-7 7', stop: 'M6 6h12v12H6z', external: 'M14 3h7v7M21 3l-11 11M10 3H3v18h18v-7',
  info: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 8v6M12 7h.01',
  image: 'M3 4h18v16H3zM3 16l6-6 5 5 3-3 4 4M16 8h.01',
  network: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18ZM3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z',
  shield: 'm12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6ZM8 12l3 3 5-6',
  close: 'm6 6 12 12M18 6 6 18', minimize: 'M5 12h14', maximize: 'M5 5h14v14H5z', check: 'm5 12 4 4L19 6',
}
</script>
<template><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path :d="shapes[name] ?? shapes.info" /></svg></template>
