import { execFileSync } from 'node:child_process';
import path from 'node:path';

export default function globalSetup(): void {
  const python =
    process.platform === 'win32' ? path.resolve('.venv/Scripts/python.exe') : 'python3';
  const output = path.resolve('tests/.e2e-fixtures');
  execFileSync(python, ['scripts/dg2_e2e_fixture.py', '--output', output], {
    cwd: path.resolve('.'),
    stdio: 'inherit',
  });
}
