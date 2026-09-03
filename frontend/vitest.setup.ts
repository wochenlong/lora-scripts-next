if (typeof localStorage !== "undefined") {
  localStorage.setItem("ui-configs", JSON.stringify({ language: "zh-CN" }))
} else if (typeof navigator !== "undefined") {
  Object.defineProperty(globalThis, "navigator", {
    value: { language: "zh-CN", languages: ["zh-CN"] },
    configurable: true,
    writable: true,
  })
}
