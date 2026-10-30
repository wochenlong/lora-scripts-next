export type LogSource = 'launcher' | 'service' | 'environment' | 'unknown'
export type LogLevel = 'INFO' | 'WARN' | 'ERROR' | 'UNKNOWN'
export interface LogEntry { id: number; receivedAt: number; source: LogSource; level: LogLevel; message: string; root: string; context: string | null }
export const sourceLabels: Record<LogSource, string> = { launcher: '启动器', service: '训练器服务', environment: '安装与修复', unknown: '未分类' }
// 在进入页面缓冲前脱敏，复制、导出和选中详情也只使用脱敏后的内容。
export function redactLog(value: string): string {
  return value
    .replace(/(https?:\/\/)[^/\s]+@/gi, '$1[已隐藏]@')
    .replace(/([?&](?:token|api[_-]?key|secret|password|access_token)=)[^\s&#]+/gi, '$1[已隐藏]')
    .replace(/(\b(?:authorization|proxy-authorization|cookie|set-cookie)\s*:\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n]+)/gi, '$1[已隐藏]')
    .replace(/\b(Bearer\s+)[\w.+/=-]+/gi, '$1[已隐藏]')
    .replace(/((?:["']?)(?:token|api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|secret|authorization|proxy-authorization|cookie|set-cookie)(?:["']?)\s*[:=]\s*)(?:"[^"\r\n]*"|'[^'\r\n]*'|[^\r\n,;}]+)/gi, '$1[已隐藏]')
}
export const normalizeLogRoot = (value: string) => value.trim().replace(/\\/g, '/').replace(/\/$/, '').toLowerCase()
export function createLogEntry(id: number, line: string, root: string, context: string | null, source: LogSource = 'unknown'): LogEntry {
  const message = redactLog(line)
  const recognizedSource = /^\[训练器服务\]/.test(message) ? 'service' : source
  const level: LogLevel = /(?:\bERROR\b|\bFATAL\b|\[失败\]|Traceback|错误：)/i.test(message) ? 'ERROR'
    : /(?:\bWARN(?:ING)?\b|警告[:：])/i.test(message) ? 'WARN'
    : /(?:\bINFO\b|\[信息\])/.test(message) || source !== 'unknown' ? 'INFO' : 'UNKNOWN'
  return { id, receivedAt: Date.now(), source: recognizedSource, level, message, root, context }
}
