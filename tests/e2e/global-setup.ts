import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import path from 'node:path';

export default function globalSetup(): void {
  const python = path.resolve(
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python',
  );
  if (!existsSync(python)) {
    throw new Error(`Python virtual environment not found at ${python}; run uv sync --frozen`);
  }
  const output = path.resolve('tests/.e2e-fixtures');
  execFileSync(python, ['scripts/dg2_e2e_fixture.py', '--output', output], {
    cwd: path.resolve('.'),
    stdio: 'inherit',
  });
}
