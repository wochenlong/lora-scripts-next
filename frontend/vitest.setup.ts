if (typeof localStorage !== "undefined") {
  localStorage.removeItem("ui-configs")
}

if (typeof navigator !== "undefined") {
  Object.defineProperty(navigator, "language", { value: "zh-CN", configurable: true })
  Object.defineProperty(navigator, "languages", { value: ["zh-CN"], configurable: true })
}
