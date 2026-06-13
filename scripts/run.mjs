/**
 * Cross-platform runner for Python inside the venv.
 *
 * Usage:
 *   node scripts/run.mjs src/separate.py [args...]
 *   node scripts/run.mjs -m pytest [args...]
 *   node scripts/run.mjs -m ruff check src/ tests/
 */
import { execSync } from 'node:child_process';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const isWin = process.platform === 'win32';

const pythonBin = isWin
  ? resolve(root, '.venv', 'Scripts', 'python.exe')
  : resolve(root, '.venv', 'bin', 'python3');

const first = process.argv[2];
const rest = process.argv.slice(3).join(' ');

let cmd;
if (first?.startsWith('-')) {
  // Flag-based invocation: -m module ...
  cmd = `"${pythonBin}" ${first} ${rest}`;
} else if (first) {
  // Script invocation: path/to/file.py ...
  const script = resolve(root, first);
  cmd = `"${pythonBin}" "${script}" ${rest}`;
} else {
  console.error('Usage: node scripts/run.mjs <script.py | -m module> [args...]');
  process.exit(1);
}

try {
  execSync(cmd, { cwd: root, stdio: 'inherit' });
} catch {
  process.exit(1);
}
