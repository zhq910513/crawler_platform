#!/usr/bin/env node
const fs = require('fs')
const target = (process.argv[2] || process.env.npm_config_registry || 'https://registry.npmjs.org').replace(/\/+$/, '')
const lockPath = 'package-lock.json'
if (!fs.existsSync(lockPath)) {
  process.exit(0)
}
const data = JSON.parse(fs.readFileSync(lockPath, 'utf8'))
let changed = 0
const prefixes = [
  'https://registry.npmjs.org/',
  'http://registry.npmjs.org/',
  'https://registry.npmmirror.com/',
  'http://registry.npmmirror.com/'
]
function normalize(value) {
  if (typeof value !== 'string') return value
  for (const prefix of prefixes) {
    if (value.startsWith(prefix)) {
      const next = `${target}/${value.slice(prefix.length)}`
      if (next !== value) changed += 1
      return next
    }
  }
  return value
}
function walk(node) {
  if (!node || typeof node !== 'object') return
  if (Array.isArray(node)) {
    for (const item of node) walk(item)
    return
  }
  for (const key of Object.keys(node)) {
    if (key === 'resolved') {
      node[key] = normalize(node[key])
    } else {
      walk(node[key])
    }
  }
}
walk(data)
fs.writeFileSync(lockPath, `${JSON.stringify(data, null, 2)}\n`)
console.log(`normalized package-lock resolved registry to ${target}; changed=${changed}`)
