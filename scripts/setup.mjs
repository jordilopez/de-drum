/**
 * Cross-platform setup script.
 * Creates a Python virtual environment and installs dependencies.
 * Runs automatically after `npm install`.
 */
import { execSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '..');
const isWin = process.platform === 'win32';

const pythonCmd = isWin ? 'python' : 'python3';
const venvPath = resolve(root, '.venv');

// 1. Create virtual environment if it doesn't exist
if (!existsSync(venvPath)) {
  console.log(`Creating virtual environment at .venv/ ...`);
  execSync(`${pythonCmd} -m venv .venv`, { cwd: root, stdio: 'inherit' });
}

// 2. Upgrade pip
const pipCmd = isWin
  ? `"${resolve(venvPath, 'Scripts', 'pip.exe')}"`
  : `"${resolve(venvPath, 'bin', 'pip')}"`;

console.log('Upgrading pip...');
execSync(`${pipCmd} install --upgrade pip -q`, { cwd: root, stdio: 'inherit' });

// 3. Install requirements
console.log('Installing Python dependencies...');
execSync(`${pipCmd} install -r requirements.txt -q`, {
  cwd: root,
  stdio: 'inherit',
});

console.log('Setup complete.');
