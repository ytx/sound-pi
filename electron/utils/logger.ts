import fs from 'fs';

export interface LogEntry {
  timestamp: string;
  level: 'info' | 'warn' | 'error';
  tag: string;
  message: string;
}

const MAX_ENTRIES = 500;
const entries: LogEntry[] = [];

function push(level: LogEntry['level'], tag: string, message: string): void {
  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    tag,
    message,
  };
  entries.push(entry);
  if (entries.length > MAX_ENTRIES) {
    entries.splice(0, entries.length - MAX_ENTRIES);
  }
  const prefix = `[${entry.timestamp}] [${level.toUpperCase()}] [${tag}]`;
  if (level === 'error') {
    console.error(prefix, message);
  } else if (level === 'warn') {
    console.warn(prefix, message);
  } else {
    console.log(prefix, message);
  }
}

export const logger = {
  info: (tag: string, message: string) => push('info', tag, message),
  warn: (tag: string, message: string) => push('warn', tag, message),
  error: (tag: string, message: string) => push('error', tag, message),

  getLogs(): LogEntry[] {
    return [...entries];
  },

  saveLogs(filePath: string): void {
    const lines = entries.map(
      (e) => `${e.timestamp}\t${e.level}\t${e.tag}\t${e.message}`,
    );
    fs.writeFileSync(filePath, lines.join('\n') + '\n', 'utf-8');
  },
};
