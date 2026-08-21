const [major, minor] = process.versions.node.split(".").map(Number)

if (major !== 22 || minor !== 19) {
  console.error(`Expected Node 22.19.x, received ${process.versions.node}`)
  process.exit(1)
}
