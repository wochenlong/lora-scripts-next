import { ref } from "vue"

/**
 * Whole-page drop targets: `dragenter`/`dragleave` fire for every child node, so a
 * counter keeps the highlight stable while the pointer moves across the page.
 */
export function useDragOverState() {
  const active = ref(false)
  let depth = 0
  const isFileDrag = (event: DragEvent) => Array.from(event.dataTransfer?.types ?? []).includes("Files")
  function onDragEnter(event: DragEvent) {
    if (!isFileDrag(event)) return
    depth += 1
    active.value = true
  }
  function onDragLeave(event: DragEvent) {
    if (!isFileDrag(event)) return
    depth = Math.max(0, depth - 1)
    if (!depth) active.value = false
  }
  function onDragOver(event: DragEvent) {
    if (isFileDrag(event)) event.preventDefault()
  }
  function onDrop() {
    depth = 0
    active.value = false
  }
  return { active, onDragEnter, onDragLeave, onDragOver, onDrop }
}
