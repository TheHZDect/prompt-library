#!/usr/bin/env node
// 把技能包安装到本机 agent 的全局技能目录。
// 用法：node <repo>/agents/skills/prompt-library/bin/install.mjs <目标技能目录>
// 目标目录由调用方（智能体平台）按其自身约定决定，本脚本不预设平台清单。
import { cpSync, existsSync, rmSync, mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const source = join(here, '..');                       // agents/skills/prompt-library
const repoRoot = dirname(dirname(dirname(source)));    // <repo>/agents/skills/prompt-library -> <repo>
const skillName = 'prompt-library';

if (!existsSync(join(source, 'SKILL.md'))) {
  console.error(`技能源缺失：${join(source, 'SKILL.md')}`);
  process.exit(1);
}

const roots = process.argv.slice(2).filter((a) => !a.startsWith('-'));
if (roots.length === 0) {
  console.error('缺少目标技能目录。请传入本平台的全局技能目录：');
  console.error('  node <repo>/agents/skills/prompt-library/bin/install.mjs <目标技能目录>');
  process.exit(1);
}

for (const root of roots) {
  const dst = join(root, skillName);
  mkdirSync(root, { recursive: true });
  rmSync(dst, { recursive: true, force: true });
  cpSync(source, dst, {
    recursive: true,
    filter: (p) => !/[\\/](\.cache|__pycache__|node_modules)[\\/]/.test(p + '/'),
  });
  // 把仓库根写进技能包：query_lib2 读 <dst>/bin/lib_home.txt 定位 .cache/ 与 assets/thumbs/，
  // 技能装到任何目录、任何 cwd 都不需要环境变量。
  mkdirSync(join(dst, 'bin'), { recursive: true });
  writeFileSync(join(dst, 'bin', 'lib_home.txt'), repoRoot + '\n');
  console.log(`已安装 -> ${dst}  (lib_home=${repoRoot})`);
}
console.log('\n仓库路径已写入各技能目录 bin/lib_home.txt；如需临时改道可设环境变量 PROMPT_LIB_HOME=<仓库根>。');
